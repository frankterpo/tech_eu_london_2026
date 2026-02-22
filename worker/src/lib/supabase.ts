import { createClient } from '@supabase/supabase-js'

export interface Env {
  SUPABASE_URL: string
  SUPABASE_API_KEY: string
  GEMINI_API_KEY?: string
  DUST_API_KEY?: string
  DUST_WORKSPACE_ID?: string
  LOVABLE_API_KEY?: string
  LOVABLE_BASE_URL?: string
}

export const getSupabase = (env: Env) => {
  return createClient(env.SUPABASE_URL, env.SUPABASE_API_KEY)
}
