'use client'

import { useQuery } from '@tanstack/react-query'
import { treeApi } from '@/lib/api/tree'

export const treeKeys = {
  all: ['tree'] as const,
  full: (rootId?: string, maxGen?: number) =>
    [...treeKeys.all, 'full', rootId, maxGen] as const,
  subtree: (rootId: string, maxGen?: number) =>
    [...treeKeys.all, 'subtree', rootId, maxGen] as const,
  ancestors: (memberId: string, maxGen?: number) =>
    [...treeKeys.all, 'ancestors', memberId, maxGen] as const,
  path: (fromId: string, toId: string) =>
    [...treeKeys.all, 'path', fromId, toId] as const,
}

export function useFamilyTree(rootMemberId?: string, maxGenerations = 6) {
  return useQuery({
    queryKey: treeKeys.full(rootMemberId, maxGenerations),
    queryFn: () =>
      treeApi.getFullTree({
        root_member_id: rootMemberId,
        max_generations: maxGenerations,
      }),
    staleTime: 60_000,
  })
}

export function useSubtree(rootId: string | undefined, maxGenerations = 5) {
  return useQuery({
    queryKey: treeKeys.subtree(rootId!, maxGenerations),
    queryFn: () => treeApi.getSubtree(rootId!, maxGenerations),
    enabled: !!rootId,
    staleTime: 60_000,
  })
}

export function useRelationshipPath(
  fromId: string | undefined,
  toId: string | undefined,
) {
  return useQuery({
    queryKey: treeKeys.path(fromId!, toId!),
    queryFn: () => treeApi.getRelationshipPath(fromId!, toId!),
    enabled: !!fromId && !!toId && fromId !== toId,
    retry: false,
  })
}
