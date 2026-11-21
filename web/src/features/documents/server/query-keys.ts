/**
 * The one place `documents` query keys are built. Scoped by `clanId` first, as persons', tree's and
 * events' keys are, so a clan switch refetches with no manual invalidation.
 *
 * There is no detail key: a detail read mints a signed URL that expires, so it is fetched when the
 * file is opened and never cached (`useOpenDocument`).
 */

type ClanId = string | null

const ROOT = 'documents' as const

export const documentsKeys = {
  all: (clanId: ClanId) => [ROOT, clanId] as const,
  lists: (clanId: ClanId) => [...documentsKeys.all(clanId), 'list'] as const,
  list: (clanId: ClanId, personId: string | null) =>
    [...documentsKeys.lists(clanId), personId ?? 'all'] as const,
}
