import { createBrowserClient } from '@supabase/ssr'
import {
  createMissingSupabaseEnvError,
  getSupabaseEnv,
} from '@/lib/supabase/config'

export function createClientOrNull() {
  const env = getSupabaseEnv()

  if (!env) {
    return null
  }

  return createBrowserClient(env.url, env.anonKey)
}

export function createClient() {
  const client = createClientOrNull()

  if (!client) {
    throw createMissingSupabaseEnvError()
  }

  return client
}
