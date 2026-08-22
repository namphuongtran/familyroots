import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { createMissingSupabaseEnvError, getSupabaseEnv } from '@/lib/supabase/config'

export async function createClientOrNull() {
  const cookieStore = await cookies()
  const env = getSupabaseEnv()

  if (!env) {
    return null
  }

  return createServerClient(env.url, env.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options as Parameters<typeof cookieStore.set>[2]),
          )
        } catch {
          // setAll called from a Server Component — can be safely ignored if
          // middleware is refreshing user sessions
        }
      },
    },
  })
}

export async function createClient() {
  const client = await createClientOrNull()

  if (!client) {
    throw createMissingSupabaseEnvError()
  }

  return client
}
