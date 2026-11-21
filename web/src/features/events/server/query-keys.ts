/**
 * The one place `events` query keys are built. Scoped by `clanId` first, as persons' and tree's
 * keys are, so a clan switch refetches with no manual invalidation.
 */

type ClanId = string | null

const ROOT = 'events' as const

export const eventsKeys = {
  all: (clanId: ClanId) => [ROOT, clanId] as const,
  upcoming: (clanId: ClanId, days: number) =>
    [...eventsKeys.all(clanId), 'upcoming', days] as const,
}
