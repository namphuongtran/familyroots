'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { relationshipsApi } from '@/lib/api/relationships'
import type { RelationshipCreateInput, RelationshipUpdateInput } from '@/lib/types'
import { memberKeys } from './useMembers'

export function useRelationshipMutations(memberId?: string) {
  const qc = useQueryClient()

  const invalidateMember = () => {
    if (memberId) {
      qc.invalidateQueries({ queryKey: memberKeys.relationships(memberId) })
    }
    // Also invalidate tree since relationships affect it
    qc.invalidateQueries({ queryKey: ['tree'] })
  }

  const create = useMutation({
    mutationFn: (input: RelationshipCreateInput) => relationshipsApi.create(input),
    onSuccess: invalidateMember,
  })

  const update = useMutation({
    mutationFn: ({ id, ...input }: RelationshipUpdateInput & { id: string }) =>
      relationshipsApi.update(id, input),
    onSuccess: invalidateMember,
  })

  const remove = useMutation({
    mutationFn: (id: string) => relationshipsApi.delete(id),
    onSuccess: invalidateMember,
  })

  return { create, update, remove }
}
