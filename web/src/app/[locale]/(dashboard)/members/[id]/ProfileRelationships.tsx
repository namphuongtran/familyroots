'use client'

import { RelationshipsAside } from '@/features/relationships'
import { useInvalidateTree } from '@/features/tree'
import { useClientRequestContext } from '@/shared/http/context.client'

/**
 * The profile page is a Server Component, so the tree invalidation that `relationships` cannot
 * import (`tree` imports it) is wired here, in a client wrapper, as `TreeScreen` does.
 */
export function ProfileRelationships({ personId }: { personId: string }) {
  const { context } = useClientRequestContext()
  const invalidateTree = useInvalidateTree(context.clanId)
  return <RelationshipsAside personId={personId} onChanged={invalidateTree} />
}
