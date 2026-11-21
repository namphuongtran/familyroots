/**
 * The one place `tree` query keys are built. Scoped by `clanId` first, as persons' keys are, so
 * a clan switch refetches with no manual invalidation.
 */

import type { GetFocusQuery, GetTreeQuery } from '../api/tree-api'

type ClanId = string | null

const ROOT = 'tree' as const

export const treeKeys = {
  all: (clanId: ClanId) => [ROOT, clanId] as const,
  full: (clanId: ClanId, query: GetTreeQuery) => [...treeKeys.all(clanId), 'full', query] as const,
  focus: (clanId: ClanId, personId: string, query: GetFocusQuery) =>
    [...treeKeys.all(clanId), 'focus', personId, query] as const,
}
