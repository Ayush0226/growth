import { supabase } from './supabase'

const baseUrl = (import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : 'https://business-growth-platform-api.onrender.com')).replace(/\/$/, '')

export type InstagramConnection = {
  connected: boolean
  username?: string
  account_type?: string
  publishing_enabled?: boolean
  comments_enabled?: boolean
  messages_enabled?: boolean
  insights_enabled?: boolean
  granted_permissions?: string[]
  provider_account_id?: string
  token_expires_at?: string
  webhook_subscribed?: boolean
  last_event_received_at?: string | null
  webhook_error?: string
}

let cacheUser = ''
let cacheVersion = 0
const readValues = new Map<string, { data: unknown; expires: number; stored: number }>()
const reads = new Map<string, Promise<unknown>>()
export function setApiUser(id: string) {
  if (cacheUser !== id) { cacheUser = id; clearReadCache() }
}
export function clearReadCache() { cacheVersion++; readValues.clear(); reads.clear() }
export function getCached<T>(path: string): T | undefined {
  const value = readValues.get(`${cacheUser}:${path}`)
  return value && Date.now() - value.stored < 300_000 ? value.data as T : undefined
}
async function read<T>(path: string, ttl: number, refresh = false): Promise<T> {
  const { data } = await supabase.auth.getSession()
  setApiUser(data.session?.user.id || '')
  if (!data.session) throw new Error('Please sign in again.')
  const key = `${cacheUser}:${path}`
  const value = readValues.get(key)
  if (!refresh && value && value.expires > Date.now()) return value.data as T
  const existing = reads.get(key)
  if (existing) return existing as Promise<T>
  const version = cacheVersion
  const promise = request<T>(refresh ? `${path}${path.includes('?') ? '&' : '?'}refresh=true` : path, undefined, data.session.user.id).then(result => {
    if (version === cacheVersion) {
      readValues.set(key, { data: result, expires: Date.now() + ttl, stored: Date.now() })
      if (readValues.size > 100) readValues.delete(readValues.keys().next().value!)
    }
    return result
  }).finally(() => { if (reads.get(key) === promise) reads.delete(key) })
  reads.set(key, promise)
  return promise
}
function pagedPath(path: string, after?: string) { return after ? `${path}?after=${encodeURIComponent(after)}` : path }
async function request<T>(path: string, init?: RequestInit, expectedUser?: string): Promise<T> {
  const { data } = await supabase.auth.getSession()
  if (!data.session) throw new Error('Please sign in again.')
  if (expectedUser && data.session.user.id !== expectedUser) throw new Error('Your account changed. Please refresh this page.')
  const send = (token: string) => fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), Authorization: `Bearer ${token}`, ...init?.headers },
  })
  let response = await send(data.session.access_token)
  if (response.status === 401) {
    const refreshed = await supabase.auth.refreshSession()
    if (refreshed.error || !refreshed.data.session) throw new Error('Your session expired. Please sign in again.')
    if (refreshed.data.session.user.id !== data.session.user.id) throw new Error('Your account changed. Please refresh this page.')
    response = await send(refreshed.data.session.access_token)
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((item: {msg?: string}) => item.msg || String(item)).join('; ') : body.detail
    throw new Error(typeof detail === 'string' ? detail : 'Request failed. Please retry.')
  }
  if (init?.method && init.method !== 'GET') clearReadCache()
  return body as T
}

export const api = {
  accessStatus: () => request<{approved:boolean;setup_ready:boolean;revoked:boolean}>('/api/access'),
  redeemAccess: (code:string) => request<{approved:boolean}>('/api/access/redeem',{method:'POST',body:JSON.stringify({code})}),
  chatbot: () => request<ChatbotStatus>('/api/chatbot'),
  saveChatbot: (config: BotInput) => request<BusinessBot>('/api/chatbot', {method:'PUT',body:JSON.stringify(config)}),
  enableChatbot: (enabled:boolean,updated_at:string) => request<BusinessBot>('/api/chatbot/enabled',{method:'POST',body:JSON.stringify({enabled,updated_at})}),
  previewChatbot: (config:BotInput,text:string) => request<{reply:string;handoff:boolean;sends_message:false}>('/api/chatbot/preview',{method:'POST',body:JSON.stringify({...config,text})}),
  resumeChatbot: (connection_id:string,sender_id:string) => request('/api/chatbot/contacts/resume',{method:'POST',body:JSON.stringify({connection_id,sender_id})}),
  workspace: () => request<{workspace: {workspace_id: string, workspaces: {name: string}} | null}>('/api/workspaces'),
  provisionWorkspace: (name: string) => request<{ workspace_id: string }>('/api/workspaces', { method: 'POST', body: JSON.stringify({ name }) }),
  instagramStatus: (refresh = false) => read<InstagramConnection>('/api/integrations/instagram', 10_000, refresh),
  instagramConnectUrl: (includeInsights = false) => request<{ authorization_url: string }>(`/api/integrations/instagram/connect?include_insights=${includeInsights}`, { method: 'POST' }),
  disconnectInstagram: () => request<{ status: string }>('/api/integrations/instagram/disconnect', { method: 'POST' }),
  subscribeInstagram: () => request<{subscribed: boolean}>('/api/integrations/instagram/subscribe', {method: 'POST'}),
  automationRules: () => request<{items: AutomationRule[]}>('/api/automations'),
  saveAutomationRule: (rule: AutomationInput, id?: string) => request<AutomationRule>(id ? `/api/automations/${id}` : '/api/automations', {method: id ? 'PUT' : 'POST', body: JSON.stringify(rule)}),
  automationActivity: () => request<AutomationActivity>('/api/automations/activity'),
  previewAutomation: (text: string, keywords: string[]) => request<{matched: boolean}>('/api/automations/preview', {method: 'POST', body: JSON.stringify({text,keywords})}),
  uploadMedia: (file: File) => { const body = new FormData(); body.append('file', file); return request<{ id: string, width: number, height: number }>('/api/media', { method: 'POST', body }) },
  createPost: (payload: { caption: string, media_asset_id?: string, media_asset_ids?: string[], request_id?: string, enqueue_only?: boolean, scheduled_for?: string, timezone: string, approved: boolean, publish_now: boolean }) => request<{ job: CalendarItem }>('/api/content/posts', { method: 'POST', body: JSON.stringify(payload) }),
  calendar: () => request<{ items: CalendarItem[] }>('/api/content/calendar'),
  calendarSummary: (start:string,end:string,timezone:string,refresh=false) => read<CalendarSummary>(`/api/calendar/summary?${new URLSearchParams({start,end,timezone})}`,30_000,refresh),
  calendarDay: (on:string,kind:CalendarKind,timezone:string,offset=0) => request<CalendarDay>(`/api/calendar/day?${new URLSearchParams({on,kind,timezone,offset:String(offset)})}`),
  dailyInsights: (on:string,timezone:string,refresh=false) => read<Insights>(`/api/instagram/insights?${new URLSearchParams({on,timezone})}`,60_000,refresh),
  publishJob: (id: string) => request<CalendarItem>(`/api/publishing/jobs/${id}/publish`, { method: 'POST' }),
  updateCalendarItem: (id: string, payload: {caption?:string, scheduled_for?:string}) => request<CalendarItem>(`/api/content/calendar/${id}`, {method:'PATCH', body:JSON.stringify(payload)}),
  cancelCalendarItem: (id: string) => request<CalendarItem>(`/api/content/calendar/${id}`, {method:'DELETE'}),
  media: (after?: string, refresh = false) => read<InstagramPage<InstagramMedia>>(pagedPath('/api/instagram/media', after), 30_000, refresh),
  comments: (mediaId:string, after?: string, refresh = false) => read<InstagramPage<InstagramComment>>(pagedPath(`/api/instagram/media/${mediaId}/comments`, after), 10_000, refresh),
  replyComment: (id:string,message:string) => request(`/api/instagram/comments/${id}/reply`,{method:'POST',body:JSON.stringify({message})}),
  hideComment: (id:string,hidden=true) => request(`/api/instagram/comments/${id}/hide?hidden=${hidden}`,{method:'POST'}),
  deleteComment: (id:string) => request(`/api/instagram/comments/${id}`,{method:'DELETE'}),
  conversations: (after?: string, refresh = false) => read<InstagramPage<Conversation>>(pagedPath('/api/instagram/conversations', after), 10_000, refresh),
  messages: (id:string, after?: string, refresh = false) => read<InstagramPage<DirectMessage>>(pagedPath(`/api/instagram/conversations/${id}/messages`, after), 5_000, refresh),
  sendMessage: (recipientId:string,message:string) => request<{message_id?:string;id?:string}>(`/api/instagram/messages/${recipientId}`,{method:'POST',body:JSON.stringify({message})}),
  insights: (refresh = false) => read<Insights>('/api/instagram/insights', 60_000, refresh),
}

export type BotInput={business_name:string;role:'support'|'sales'|'feedback';knowledge:string;instructions:string;handoff_message:string;daily_limit:number}
export type BusinessBot=BotInput&{enabled:boolean;updated_at:string}
export type ChatbotStatus={config:BusinessBot|null;setup_ready:boolean;provider_ready:boolean;provider:string;usage:{live:number;preview:number};paused_contacts:{connection_id:string;sender_id:string;reason:string;updated_at:string}[]}

export type AutomationInput = {name: string; trigger: 'welcome' | 'dm_keyword' | 'comment_keyword'; keywords: string[]; media_ids: string[]; reply_text: string; enabled: boolean; daily_limit: number; cooldown_minutes: number}
export type AutomationRule = AutomationInput & {id: string; created_at: string}
export type AutomationActivity = {events: {id:string;kind:string;status:string;detail?:string;received_at:string}[];deliveries:{id:string;rule_id:string;status:string;reply_text:string;detail?:string;created_at:string}[]}

export type InstagramPage<T> = {data:T[];paging?:{cursors?:{after?:string;before?:string};has_more?:boolean};attachments_unavailable?:boolean}

export type InstagramMedia={id:string;caption?:string;media_url?:string;thumbnail_url?:string;permalink:string;timestamp:string;comments_count?:number;like_count?:number}
export type InstagramComment={id:string;text:string;timestamp:string;username?:string;from?:{id?:string;username?:string};like_count?:number;hidden?:boolean;replies?:{data:InstagramComment[]}}
export type MessageAttachment={id?:string;mime_type?:string;name?:string;file_url?:string;image_data?:{url?:string;preview_url?:string};video_data?:{url?:string};payload?:{url?:string}}
export type DirectMessage={id:string;created_time:string;message?:string;from:{id:string;username?:string};to?:{data:{id:string;username?:string}[]};attachments?:{data:MessageAttachment[]};shares?:{data:{link?:string;name?:string}[]}}
export type Conversation={id:string;updated_time:string;participants:{data:{id:string;username?:string}[]};messages?:{data:DirectMessage[]}}
export type Insights={profile:{followers_count?:number;follows_count?:number;media_count?:number;username?:string};metrics:{name:string;total_value?:{value:number};values?:{value:number}[]}[];metrics_status?:'available'|'unavailable'|'future';requested_date?:string;provisional?:boolean}

export type CalendarKind='posts'|'published'|'automation'|'deliveries'|'ai'
export type CalendarSummary={days:Record<string,Record<CalendarKind,number>>;truncated_categories:CalendarKind[];timezone:string}
export type CalendarRecord=Partial<CalendarItem>&{id:string;status:string;kind?:string;detail?:string;received_at?:string;processed_at?:string;created_at?:string;purpose?:'preview'|'live';reply_text?:string}
export type CalendarDay={items:CalendarRecord[];has_more:boolean;next_offset:number}

export type CalendarItem = {
  id: string
  status: string
  scheduled_for: string
  published_at?: string
  provider_permalink?: string
  failure_message?: string
  content_targets: { timezone: string, content_drafts: { caption: string, post_type: string } }
}
