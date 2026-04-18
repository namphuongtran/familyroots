const CURRENT_CLAN_COOKIE = 'current_clan_id'
const ONE_YEAR_IN_SECONDS = 60 * 60 * 24 * 365

export function persistCurrentClanId(clanId: string): void {
  if (typeof window === 'undefined') {
    return
  }

  localStorage.setItem(CURRENT_CLAN_COOKIE, clanId)
  document.cookie = `${CURRENT_CLAN_COOKIE}=${encodeURIComponent(clanId)}; path=/; max-age=${ONE_YEAR_IN_SECONDS}; samesite=lax`
}

export function clearCurrentClanId(): void {
  if (typeof window === 'undefined') {
    return
  }

  localStorage.removeItem(CURRENT_CLAN_COOKIE)
  document.cookie = `${CURRENT_CLAN_COOKIE}=; path=/; max-age=0; samesite=lax`
}
