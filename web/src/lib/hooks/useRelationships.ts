'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createMarriage,
  createParentChild,
  deleteMarriage,
  deleteParentChild,
  updateMarriage,
  updateParentChild,
} from '@/application/relationships/use-cases/relationship-commands'
import {
  marriageCommandRepository,
  parentChildCommandRepository,
} from '@/infrastructure/relationships/relationship-command-repository'
import type {
  MarriageCreateInput,
  MarriageUpdateInput,
  ParentChildCreateInput,
  ParentChildUpdateInput,
} from '@/lib/types'

export function useMarriageMutations() {
  const qc = useQueryClient()

  const invalidateTree = () => {
    qc.invalidateQueries({ queryKey: ['tree'] })
  }

  const create = useMutation({
    mutationFn: (input: MarriageCreateInput) => createMarriage(marriageCommandRepository, input),
    onSuccess: invalidateTree,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: MarriageUpdateInput & { id: string }) =>
      updateMarriage(marriageCommandRepository, id, input),
    onSuccess: invalidateTree,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteMarriage(marriageCommandRepository, id),
    onSuccess: invalidateTree,
  })

  return { create, update, remove }
}

export function useParentChildMutations() {
  const qc = useQueryClient()

  const invalidateTree = () => {
    qc.invalidateQueries({ queryKey: ['tree'] })
  }

  const create = useMutation({
    mutationFn: (input: ParentChildCreateInput) =>
      createParentChild(parentChildCommandRepository, input),
    onSuccess: invalidateTree,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: ParentChildUpdateInput & { id: string }) =>
      updateParentChild(parentChildCommandRepository, id, input),
    onSuccess: invalidateTree,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteParentChild(parentChildCommandRepository, id),
    onSuccess: invalidateTree,
  })

  return { create, update, remove }
}
