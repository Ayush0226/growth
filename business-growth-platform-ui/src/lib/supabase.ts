import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!url || !key) throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required')

export const supabase = createClient(url, key, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
})

export async function googleSignInEnabled():Promise<boolean>{
  const response=await fetch(`${url.replace(/\/$/,'')}/auth/v1/settings`,{headers:{apikey:key}})
  if(!response.ok)throw new Error('Could not check Google sign-in availability.')
  const settings=await response.json()
  return settings.external?.google===true
}
