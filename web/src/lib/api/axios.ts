import axios from 'axios'
import { createClient } from '@/lib/supabase/client'
import { getRequestContext } from '@/infrastructure/http/request-context'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

// ── Request interceptor: attach JWT + request context ─────────────────────────
api.interceptors.request.use(async (config) => {
  try {
    const supabase = createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()

    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`
    }
  } catch {
    // getSession may throw in SSR context — ignore
  }

  const context = getRequestContext()
  config.headers['Accept-Language'] = context.locale

  if (context.currentClanId) {
    config.headers['X-Current-Clan-Id'] = context.currentClanId
  }

  return config
})

// ── Response interceptor: handle 401 globally ────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      try {
        const supabase = createClient()
        await supabase.auth.signOut()
      } finally {
        const { locale } = getRequestContext()
        window.location.href = `/${locale}/login`
      }
    }
    return Promise.reject(error)
  },
)

export default api
