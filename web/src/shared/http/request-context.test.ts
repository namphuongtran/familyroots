import { describe, expect, it } from 'vitest'
import { localeFromPathname, normalizeLocale, parseClanCookie } from './request-context'

describe('normalizeLocale', () => {
  it('accepts every supported locale', () => {
    for (const locale of ['vi', 'en', 'zh', 'fr'] as const) {
      expect(normalizeLocale(locale)).toBe(locale)
    }
  })

  it('falls back to Vietnamese for anything unsupported', () => {
    expect(normalizeLocale('de')).toBe('vi')
    expect(normalizeLocale('')).toBe('vi')
    expect(normalizeLocale(null)).toBe('vi')
    expect(normalizeLocale(undefined)).toBe('vi')
  })

  it('is case-insensitive and tolerates a region suffix', () => {
    expect(normalizeLocale('EN')).toBe('en')
    expect(normalizeLocale('fr-FR')).toBe('fr')
  })
})

describe('localeFromPathname', () => {
  it('reads the always-present locale prefix', () => {
    expect(localeFromPathname('/vi/members')).toBe('vi')
    expect(localeFromPathname('/en/tree')).toBe('en')
    expect(localeFromPathname('/fr')).toBe('fr')
  })

  it('falls back to Vietnamese when there is no usable prefix', () => {
    expect(localeFromPathname('/')).toBe('vi')
    expect(localeFromPathname('/members')).toBe('vi')
    expect(localeFromPathname('')).toBe('vi')
  })
})

describe('parseClanCookie', () => {
  const validClanId = '4bf92f35-77b3-4da6-a3ce-929d0e0e4736'

  it('accepts a well-formed UUID, case-insensitively', () => {
    expect(parseClanCookie(validClanId)).toBe(validClanId)
    expect(parseClanCookie(validClanId.toUpperCase())).toBe(validClanId.toUpperCase())
  })

  it('treats a missing cookie as no clan selected', () => {
    expect(parseClanCookie(null)).toBeNull()
    expect(parseClanCookie(undefined)).toBeNull()
    expect(parseClanCookie('')).toBeNull()
  })

  it('treats an unparseable cookie the same as a missing one, rather than forwarding it', () => {
    expect(parseClanCookie('not-a-uuid')).toBeNull()
    expect(parseClanCookie('11111111-1111-1111-1111-111111111111; DROP TABLE clans;')).toBeNull()
    expect(parseClanCookie('   ')).toBeNull()
    expect(parseClanCookie('4bf92f35-77b3-4da6-a3ce-929d0e0e473')).toBeNull() // one char short
  })
})
