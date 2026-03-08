'use client'

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '@/lib/api/documents'

export const documentKeys = {
  all: ['documents'] as const,
  list: (memberId?: string) => [...documentKeys.all, 'list', memberId ?? 'all'] as const,
  detail: (id: string) => [...documentKeys.all, 'detail', id] as const,
}

export function useDocuments(memberId?: string) {
  return useInfiniteQuery({
    queryKey: documentKeys.list(memberId),
    queryFn: ({ pageParam }) => documentsApi.list({ member_id: memberId, cursor: pageParam as string | undefined }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
    staleTime: 60_000,
  })
}

export function useDocumentMutations() {
  const qc = useQueryClient()

  const uploadDocument = useMutation({
    mutationFn: ({ file, title, member_id }: { file: File; title: string; member_id?: string }) =>
      documentsApi.upload(file, { title, member_id, document_type: 'other' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.all }),
  })

  const deleteDocument = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.all }),
  })

  return { uploadDocument, deleteDocument }
}

