/**
 * The one place `admin` query keys are built. Scoped by `clanId` first, as every slice's keys are,
 * so a clan switch refetches with no manual invalidation.
 */

type ClanId = string | null

const ROOT = 'admin' as const

export const adminKeys = {
  all: (clanId: ClanId) => [ROOT, clanId] as const,
  profile: (clanId: ClanId) => [...adminKeys.all(clanId), 'profile'] as const,
  stats: (clanId: ClanId) => [...adminKeys.all(clanId), 'stats'] as const,
  users: (clanId: ClanId) => [...adminKeys.all(clanId), 'users'] as const,
}
