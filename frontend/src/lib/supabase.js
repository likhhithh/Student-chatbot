import { createClient } from '@supabase/supabase-js'

const url  = import.meta.env.VITE_SUPABASE_URL
const key  = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!url || url.includes('YOUR_PROJECT_ID')) {
  console.warn('[StudyGPT] Supabase URL not configured — set VITE_SUPABASE_URL in frontend/.env.local')
}

export const supabase = createClient(url, key)
