export const SUPPORTED_LOCALES = ['vi', 'en', 'zh', 'fr'] as const

export type LocaleCode = (typeof SUPPORTED_LOCALES)[number]

/** Vietnamese is the product default, not a fallback of convenience. */
export const DEFAULT_LOCALE: LocaleCode = 'vi'

export type ClanId = string

/**
 * @deprecated Legacy shape, kept only so `src/infrastructure/http/request-context.ts`
 * keeps compiling until the slice PRs delete it. New code uses the `RequestContext`
 * exported from `@/shared/http/request-context`, which also carries the access token
 * and works in both runtimes.
 */
export interface LegacyRequestContext {
  locale: LocaleCode
  currentClanId?: ClanId
}

export type { LegacyRequestContext as RequestContext }
