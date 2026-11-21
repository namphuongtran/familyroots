import { describe, expect, it } from 'vitest'
import { buildCsp, securityHeaders } from './security-headers'

const env = {
  NEXT_PUBLIC_SUPABASE_URL: 'https://abc.supabase.co',
  NEXT_PUBLIC_API_ORIGIN: 'https://api.example.com',
} as unknown as NodeJS.ProcessEnv

describe('security headers', () => {
  it('forbids framing and allows the API and Supabase origins', () => {
    const csp = buildCsp(env, false)
    expect(csp).toContain("frame-ancestors 'none'")
    expect(csp).toContain('https://api.example.com')
    expect(csp).toContain('https://abc.supabase.co')
    expect(csp).not.toContain('unsafe-eval')
  })
  it('sends HSTS only in production', () => {
    const keys = (dev: boolean) => securityHeaders(env, dev).map((h) => h.key)
    expect(keys(false)).toContain('Strict-Transport-Security')
    expect(keys(true)).not.toContain('Strict-Transport-Security')
  })
})
