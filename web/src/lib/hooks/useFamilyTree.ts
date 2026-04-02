'use client'

import { useQuery } from '@tanstack/react-query'
import {
  getAncestors,
  getFullTree,
  getRelationshipPath,
  getSubtree,
} from '@/application/tree/use-cases/tree-queries'
import { treeQueryRepository } from '@/infrastructure/tree/tree-query-repository'

export const treeKeys = {
  all: ['tree'] as const,
  full: (rootId?: string, maxGen?: number) =>
    [...treeKeys.all, 'full', rootId, maxGen] as const,
  subtree: (rootId: string, maxGen?: number) =>
    [...treeKeys.all, 'subtree', rootId, maxGen] as const,
  ancestors: (personId: string, maxGen?: number) =>
    [...treeKeys.all, 'ancestors', personId, maxGen] as const,
  path: (fromId: string, toId: string) =>
    [...treeKeys.all, 'path', fromId, toId] as const,
}

export function useFamilyTree(rootPersonId?: string, maxGenerations = 6) {
  return useQuery({
    queryKey: treeKeys.full(rootPersonId, maxGenerations),
    queryFn: () =>
      getFullTree(treeQueryRepository, {
        root_person_id: rootPersonId,
        max_generations: maxGenerations,
      }),
    staleTime: 60_000,
  })
}

export function useSubtree(rootId: string | undefined, maxGenerations = 5) {
  return useQuery({
    queryKey: treeKeys.subtree(rootId!, maxGenerations),
    queryFn: () => getSubtree(treeQueryRepository, rootId!, maxGenerations),
    enabled: !!rootId,
    staleTime: 60_000,
  })
}

export function useAncestors(personId: string | undefined, maxGenerations = 10) {
  return useQuery({
    queryKey: treeKeys.ancestors(personId!, maxGenerations),
    queryFn: () => getAncestors(treeQueryRepository, personId!, maxGenerations),
    enabled: !!personId,
    staleTime: 60_000,
  })
}

export function useRelationshipPath(
  fromId: string | undefined,
  toId: string | undefined,
) {
  return useQuery({
    queryKey: treeKeys.path(fromId!, toId!),
    queryFn: () => getRelationshipPath(treeQueryRepository, fromId!, toId!),
    enabled: !!fromId && !!toId && fromId !== toId,
    retry: false,
  })
}
