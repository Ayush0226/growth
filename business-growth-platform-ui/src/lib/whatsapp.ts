import { request } from './api'

export type WAConnection = {
  id: string; status: string; waba_id: string; phone_number_id: string;
  display_phone_number?: string; verified_name?: string; billing_acknowledged: boolean;
  ai_enabled: boolean; business_name: string; knowledge: string; instructions: string;
  handoff_message: string; ai_daily_limit: number; updated_at: string;
}
export type WAStatus = {
  enabled: boolean; connected: boolean; setup_ready: boolean; signup_ready: boolean;
  app_id: string; config_id?: string; graph_version: string; billing_url: string; pricing_url: string;
  connection?: WAConnection; ai_ready: boolean;
  usage?: {tracked_service_deliveries: number; note: string};
}
export type WAContact = {id: string; wa_id: string; name: string; opted_in: boolean; opted_out: boolean; consent_source: string; automation_paused: boolean; window_ends_at?: string}
export type WAMessage = {id: string; contact_wa_id: string; direction: string; text: string; status: string; detail?: string; occurred_at: string; created_at: string; message_type: string; purpose: string}
export type WARuleInput = {name: string; trigger: 'welcome'|'keyword'; keywords: string[]; reply_text: string; daily_limit: number; cooldown_minutes: number}
export type WARule = WARuleInput & {id: string; enabled: boolean; updated_at: string}
export type WATemplate = {id: string; name: string; language: string; category: string; status: string; sendable: boolean; parameter_count: number; components: {type: string; text?: string}[]}
export type WARecipient = {wa_id: string; parameters: string[]}
export type WACampaign = {id: string; name: string; status: string; template: WATemplate; recipients: WARecipient[]; recipient_count: number; scheduled_for: string; counts: Record<string, number>; detail: string}

export const waGet = <T,>(path: string) => request<T>(`/api/whatsapp${path}`)
export const waSend = <T,>(path: string, body: unknown = {}, method = 'POST') => request<T>(`/api/whatsapp${path}`, {method, body: JSON.stringify(body)})

type MetaResponse = {authResponse?: {code?: string}}
type MetaSDK = {init(options: Record<string, unknown>): void; login(callback: (response: MetaResponse) => void, options: Record<string, unknown>): void}
declare global { interface Window { FB?: MetaSDK } }
let loading: Promise<void> | undefined

export function loadMetaSDK(status: WAStatus): Promise<void> {
  if (!loading) loading = new Promise<void>((resolve, reject) => {
    if (window.FB) { resolve(); return }
    const existing = document.getElementById('growthboard-meta-sdk')
    if (existing) existing.remove()
    const script = document.createElement('script')
    script.id = 'growthboard-meta-sdk'; script.src = 'https://connect.facebook.net/en_US/sdk.js'; script.async = true
    script.onload = () => resolve(); script.onerror = () => { loading = undefined; reject(new Error('Meta connection could not load. Check your browser settings and try again.')) }
    document.head.appendChild(script)
  })
  return loading.then(() => {
    if (!window.FB) throw new Error('Meta connection is unavailable. Please refresh.')
    window.FB.init({appId: status.app_id, version: status.graph_version, xfbml: false, cookie: false})
  })
}

export function connectMeta(status: WAStatus, state: string, registrationPin?: string): Promise<WAConnection> {
  return new Promise((resolve, reject) => {
    let assets: {waba_id: string; phone_number_id: string} | undefined
    let code: string | undefined
    let completing = false
    const cleanup = () => { clearTimeout(timer); window.removeEventListener('message', listener) }
    const fail = (error: Error) => { cleanup(); reject(error) }
    const complete = () => {
      if (!code || !assets || completing) return
      completing = true
      cleanup()
      waSend<WAConnection>('/signup/complete', {state, code, ...assets, registration_pin: registrationPin || null}).then(resolve).catch(reject)
    }
    const listener = (event: MessageEvent) => {
      if (!['https://www.facebook.com', 'https://web.facebook.com'].includes(event.origin)) return
      try {
        const item = typeof event.data === 'string' ? JSON.parse(event.data) : event.data
        if (item?.type !== 'WA_EMBEDDED_SIGNUP') return
        if (item.event === 'CANCEL' || item.event === 'ERROR') { fail(new Error('Meta setup was cancelled or could not finish. You can try again.')); return }
        if (typeof item.data?.waba_id === 'string' && typeof item.data?.phone_number_id === 'string') {
          assets = {waba_id: item.data.waba_id, phone_number_id: item.data.phone_number_id}
          complete()
        }
      } catch { /* Ignore unrelated messages from Meta's popup. */ }
    }
    const timer = setTimeout(() => fail(new Error('Meta setup timed out. Close its window and try again.')), 10 * 60 * 1000)
    window.addEventListener('message', listener)
    if (!window.FB) { fail(new Error('Meta connection has not loaded.')); return }
    try {
      window.FB.login(response => {
        code = response.authResponse?.code
        if (!code) { fail(new Error('Connection was not authorized.')); return }
        complete()
        setTimeout(() => { if (!completing) fail(new Error('Meta did not return a business number. Complete number selection and start again.')) }, 10_000)
      }, {config_id: status.config_id, response_type: 'code', override_default_response_type: true,
          extras: {sessionInfoVersion: '3'}})
    } catch { fail(new Error('Could not open Meta. Allow popups and try again.')) }
  })
}
