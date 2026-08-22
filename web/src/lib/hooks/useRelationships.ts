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
import { personKeys } from './useMembers'

export function useMarriageMutations(personId?: string) {
  const qc = useQueryClient()

  const invalidatePerson = () => {
    if (personId) {
      qc.invalidateQueries({ queryKey: personKeys.marriages(personId) })
    }
    qc.invalidateQueries({ queryKey: ['tree'] })
  }

  const create = useMutation({
    mutationFn: (input: MarriageCreateInput) => createMarriage(marriageCommandRepository, input),
    onSuccess: invalidatePerson,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: MarriageUpdateInput & { id: string }) =>
      updateMarriage(marriageCommandRepository, id, input),
    onSuccess: invalidatePerson,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteMarriage(marriageCommandRepository, id),
    onSuccess: invalidatePerson,
  })

  return { create, update, remove }
}

export function useParentChildMutations(personId?: string) {
  const qc = useQueryClient()

  const invalidatePerson = () => {
    if (personId) {
      qc.invalidateQueries({ queryKey: personKeys.parentChild(personId) })
    }
    qc.invalidateQueries({ queryKey: ['tree'] })
  }

  const create = useMutation({
    mutationFn: (input: ParentChildCreateInput) =>
      createParentChild(parentChildCommandRepository, input),
    onSuccess: invalidatePerson,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: ParentChildUpdateInput & { id: string }) =>
      updateParentChild(parentChildCommandRepository, id, input),
    onSuccess: invalidatePerson,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteParentChild(parentChildCommandRepository, id),
    onSuccess: invalidatePerson,
  })

  return { create, update, remove }
}
