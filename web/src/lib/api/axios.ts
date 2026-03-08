import axios from 'axios'
import { createClient } from '@/lib/supabase/client'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

// ── Request interceptor: attach JWT + locale ──────────────────────────────────
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

  // Attach preferred locale from localStorage (client-side only)
  if (typeof window !== 'undefined') {
    const locale = localStorage.getItem('preferred_locale') ?? 'vi'
    config.headers['Accept-Language'] = locale
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
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export default api
