import { supabase } from './supabase'

const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type InstagramConnection = {
  connected: boolean
  username?: string
  account_type?: string
  publishing_enabled?: boolean
  comments_enabled?: boolean
  messages_enabled?: boolean
  insights_enabled?: boolean
  granted_permissions?: string[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { data } = await supabase.auth.getSession()
  if (!data.session) throw new Error('Please sign in again.')
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), Authorization: `Bearer ${data.session.access_token}`, ...init?.headers },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail ?? 'Request failed')
  return body as T
}

export const api = {
  provisionWorkspace: (name: string) => request<{ workspace_id: string }>('/api/workspaces', { method: 'POST', body: JSON.stringify({ name }) }),
  instagramStatus: () => request<InstagramConnection>('/api/integrations/instagram'),
  instagramConnectUrl: () => request<{ authorization_url: string }>('/api/integrations/instagram/connect', { method: 'POST' }),
  disconnectInstagram: () => request<{ status: string }>('/api/integrations/instagram/disconnect', { method: 'POST' }),
  uploadMedia: (file: File) => { const body = new FormData(); body.append('file', file); return request<{ id: string, width: number, height: number }>('/api/media', { method: 'POST', body }) },
  createPost: (payload: { caption: string, media_asset_id: string, scheduled_for?: string, timezone: string, approved: boolean, publish_now: boolean }) => request<{ job: CalendarItem }>('/api/content/posts', { method: 'POST', body: JSON.stringify(payload) }),
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
