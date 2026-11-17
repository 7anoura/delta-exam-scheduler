import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL?.trim()
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim()

export const authConfigurationMissing =
  !url || !/^https:\/\/[a-z0-9-]+\.supabase\.co\/?$/.test(url) || !key || key.startsWith('PASTE_') || key.startsWith('sb_secret_')

// Browser gets the publishable key and its own user session only.
// The database's service key exists ONLY in FastAPI's private .env.
export const supabase: SupabaseClient | null = authConfigurationMissing ? null : createClient(url!, key!, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
})
