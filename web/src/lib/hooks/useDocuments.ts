'use client'

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '@/lib/api/documents'

export const documentKeys = {
  all: ['documents'] as const,
  list: (personId?: string) => [...documentKeys.all, 'list', personId ?? 'all'] as const,
  detail: (id: string) => [...documentKeys.all, 'detail', id] as const,
}

export function useDocuments(personId?: string) {
  return useInfiniteQuery({
    queryKey: documentKeys.list(personId),
    queryFn: ({ pageParam }) => documentsApi.list({ person_id: personId, cursor: pageParam as string | undefined }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
    staleTime: 60_000,
  })
}

export function useDocumentMutations() {
  const qc = useQueryClient()

  const uploadDocument = useMutation({
    mutationFn: ({ file, title, person_id }: { file: File; title: string; person_id?: string }) =>
      documentsApi.upload(file, { title, person_id, document_type: 'other' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.all }),
  })

  const deleteDocument = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.all }),
  })

  return { uploadDocument, deleteDocument }
}

