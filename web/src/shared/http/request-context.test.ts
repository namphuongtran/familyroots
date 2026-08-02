import { describe, expect, it } from 'vitest'
import { localeFromPathname, normalizeLocale } from './request-context'

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
