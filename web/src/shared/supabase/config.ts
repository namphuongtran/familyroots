export const MISSING_SUPABASE_ENV_ERROR =
  'Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY environment variables.'

export function getSupabaseEnv() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!url || !anonKey) {
    return null
  }

  return { url, anonKey }
}

export function isSupabaseConfigured() {
  return getSupabaseEnv() !== null
}

export function createMissingSupabaseEnvError() {
  return new Error(MISSING_SUPABASE_ENV_ERROR)
}
