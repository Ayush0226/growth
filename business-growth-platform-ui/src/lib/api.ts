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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { data } = await supabase.auth.getSession()
  if (!data.session) throw new Error('Please sign in again.')
  const send = (token: string) => fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), Authorization: `Bearer ${token}`, ...init?.headers },
  })
  let response = await send(data.session.access_token)
  if (response.status === 401) {
    const refreshed = await supabase.auth.refreshSession()
    if (refreshed.error || !refreshed.data.session) throw new Error('Your session expired. Please sign in again.')
    response = await send(refreshed.data.session.access_token)
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((item: {msg?: string}) => item.msg || String(item)).join('; ') : body.detail
    throw new Error(typeof detail === 'string' ? detail : 'Request failed. Please retry.')
  }
  return body as T
}

export const api = {
  workspace: () => request<{workspace: {workspace_id: string, workspaces: {name: string}} | null}>('/api/workspaces'),
  provisionWorkspace: (name: string) => request<{ workspace_id: string }>('/api/workspaces', { method: 'POST', body: JSON.stringify({ name }) }),
  instagramStatus: () => request<InstagramConnection>('/api/integrations/instagram'),
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
  publishJob: (id: string) => request<CalendarItem>(`/api/publishing/jobs/${id}/publish`, { method: 'POST' }),
  updateCalendarItem: (id: string, payload: {caption?:string, scheduled_for?:string}) => request<CalendarItem>(`/api/content/calendar/${id}`, {method:'PATCH', body:JSON.stringify(payload)}),
  cancelCalendarItem: (id: string) => request<CalendarItem>(`/api/content/calendar/${id}`, {method:'DELETE'}),
  media: () => request<{data:InstagramMedia[]}>('/api/instagram/media'),
  comments: (mediaId:string) => request<{data:InstagramComment[]}>(`/api/instagram/media/${mediaId}/comments`),
  replyComment: (id:string,message:string) => request(`/api/instagram/comments/${id}/reply`,{method:'POST',body:JSON.stringify({message})}),
  hideComment: (id:string,hidden=true) => request(`/api/instagram/comments/${id}/hide?hidden=${hidden}`,{method:'POST'}),
  deleteComment: (id:string) => request(`/api/instagram/comments/${id}`,{method:'DELETE'}),
  conversations: () => request<{data:Conversation[]}>('/api/instagram/conversations'),
  messages: (id:string) => request<{data:DirectMessage[]}>(`/api/instagram/conversations/${id}/messages`),
  sendMessage: (recipientId:string,message:string) => request(`/api/instagram/messages/${recipientId}`,{method:'POST',body:JSON.stringify({message})}),
  insights: () => request<Insights>('/api/instagram/insights'),
}

export type AutomationInput = {name: string; trigger: 'welcome' | 'dm_keyword' | 'comment_keyword'; keywords: string[]; media_ids: string[]; reply_text: string; enabled: boolean; daily_limit: number; cooldown_minutes: number}
export type AutomationRule = AutomationInput & {id: string; created_at: string}
export type AutomationActivity = {events: {id:string;kind:string;status:string;detail?:string;received_at:string}[];deliveries:{id:string;rule_id:string;status:string;reply_text:string;detail?:string;created_at:string}[]}

export type InstagramMedia={id:string;caption?:string;media_url?:string;thumbnail_url?:string;permalink:string;timestamp:string;comments_count?:number;like_count?:number}
export type InstagramComment={id:string;text:string;timestamp:string;username:string;like_count?:number;hidden?:boolean;replies?:{data:InstagramComment[]}}
export type DirectMessage={id:string;created_time:string;message:string;from:{id:string;username?:string};to?:{data:{id:string;username?:string}[]}}
export type Conversation={id:string;updated_time:string;participants:{data:{id:string;username?:string}[]};messages?:{data:DirectMessage[]}}
export type Insights={profile:{followers_count?:number;follows_count?:number;media_count?:number;username?:string};metrics:{name:string;total_value?:{value:number};values?:{value:number}[]}[]}

export type CalendarItem = {
  id: string
  status: string
  scheduled_for: string
  published_at?: string
  provider_permalink?: string
  failure_message?: string
  content_targets: { timezone: string, content_drafts: { caption: string, post_type: string } }
}
