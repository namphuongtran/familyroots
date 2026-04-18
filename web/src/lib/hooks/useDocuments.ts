'use client'

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteDocument as deleteDocumentCommand,
  uploadDocument as uploadDocumentCommand,
} from '@/application/documents/use-cases/document-commands'
import { getDocument, listDocuments } from '@/application/documents/use-cases/document-queries'
import { documentCommandRepository } from '@/infrastructure/documents/document-command-repository'
import { documentQueryRepository } from '@/infrastructure/documents/document-query-repository'
import {
  documentDeleteInvalidationKeys,
  documentUploadInvalidationKeys,
} from '@/lib/hooks/query-invalidation'

export const documentKeys = {
  all: ['documents'] as const,
  list: (personId?: string) => [...documentKeys.all, 'list', personId ?? 'all'] as const,
  detail: (id: string) => [...documentKeys.all, 'detail', id] as const,
}

export function useDocuments(personId?: string) {
  return useInfiniteQuery({
    queryKey: documentKeys.list(personId),
    queryFn: ({ pageParam }) =>
      listDocuments(documentQueryRepository, {
        person_id: personId,
        cursor: pageParam as string | undefined,
      }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
    staleTime: 60_000,
  })
}

export function useDocument(id?: string) {
  return useQuery({
    queryKey: id ? documentKeys.detail(id) : [...documentKeys.all, 'detail', 'missing'],
    queryFn: () => getDocument(documentQueryRepository, id!),
    enabled: Boolean(id),
    staleTime: 60_000,
  })
}

export function useDocumentMutations() {
  const qc = useQueryClient()

  const uploadMutation = useMutation({
    mutationFn: ({ file, title, person_id }: { file: File; title: string; person_id?: string }) =>
      uploadDocumentCommand(documentCommandRepository, file, {
        title,
        person_id,
        document_type: 'other',
      }),
    onSuccess: (_data, variables) => {
      documentUploadInvalidationKeys(variables.person_id).forEach((queryKey) => {
        qc.invalidateQueries({ queryKey })
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteDocumentCommand(documentCommandRepository, id),
    onSuccess: () => {
      documentDeleteInvalidationKeys().forEach((queryKey) => {
        qc.invalidateQueries({ queryKey })
      })
    },
  })

  return { uploadDocument: uploadMutation, deleteDocument: deleteMutation }
}
