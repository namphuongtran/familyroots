'use client'

import { useInvalidateTree } from '@/features/tree'
import { RelationshipsAside } from '@/features/relationships'
import { useClientRequestContext } from '@/shared/http/context.client'

/**
 * Client boundary for the profile page's relationship aside: the page is a Server Component and
 * cannot hand a function to a client component. An edge written here can move or add a node, so
 * the tree rereads (#411).
 */
export function ProfileRelationships({ personId }: { personId: string }) {
  const { context } = useClientRequestContext()
  const invalidateTree = useInvalidateTree(context.clanId)
  return <RelationshipsAside personId={personId} onChanged={invalidateTree} />
}
