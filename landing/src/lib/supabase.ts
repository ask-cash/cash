import { createClient, type SupabaseClient } from '@supabase/supabase-js'

// The client is created lazily and only when both env vars are present, so the
// site still runs (and the form still shows its success state) before Supabase
// is configured. Set these in landing/.env — see .env.example.
const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey, { auth: { persistSession: false } }) : null

if (!supabase) {
  console.warn(
    '[cash] Supabase not configured — set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in landing/.env to store waitlist signups.',
  )
}

export interface WaitlistSignup {
  email: string
  name: string | null
  role: string | null
  use_cases: string[]
  tools: string[]
  priority: string | null
}

/** Insert a waitlist signup. Resolves to an error message, or null on success. */
export async function submitWaitlist(payload: WaitlistSignup): Promise<string | null> {
  if (!supabase) return null // not configured — treat as a soft success locally
  const { error } = await supabase.from('waitlist').insert(payload)
  if (error) {
    console.error('[cash] waitlist insert failed:', error)
    return error.message
  }
  return null
}
