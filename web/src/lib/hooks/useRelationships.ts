'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { marriagesApi, parentChildApi } from '@/lib/api/relationships'
import type { MarriageCreateInput, MarriageUpdateInput, ParentChildCreateInput, ParentChildUpdateInput } from '@/lib/types'
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
    mutationFn: (input: MarriageCreateInput) => marriagesApi.create(input),
    onSuccess: invalidatePerson,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: MarriageUpdateInput & { id: string }) =>
      marriagesApi.update(id, input),
    onSuccess: invalidatePerson,
  })

  const remove = useMutation({
    mutationFn: (id: string) => marriagesApi.delete(id),
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
    mutationFn: (input: ParentChildCreateInput) => parentChildApi.create(input),
    onSuccess: invalidatePerson,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: ParentChildUpdateInput & { id: string }) =>
      parentChildApi.update(id, input),
    onSuccess: invalidatePerson,
  })

  const remove = useMutation({
    mutationFn: (id: string) => parentChildApi.delete(id),
    onSuccess: invalidatePerson,
  })

  return { create, update, remove }
}
