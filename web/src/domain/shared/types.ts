export type LocaleCode = 'vi' | 'en' | 'zh' | 'fr'

export type ClanId = string

export interface RequestContext {
  locale: LocaleCode
  currentClanId?: ClanId
}