'use client'

/**
 * TanStack Query wrappers over `../server/documents-repository`. The caller passes the
 * `RequestContext` in, from `useClientRequestContext()`, as in the persons, tree and events hooks.
 */

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { RequestContext } from '@/shared/http/request-context'
import {
  deleteDocument,
  getDocument,
  listDocuments,
  uploadDocument,
  type UploadDocumentInput,
} from '../server/documents-repository'
import { documentsKeys } from '../server/query-keys'

export interface DocumentsQueryOptions {
  context: RequestContext
  refreshAuth?: () => Promise<RequestContext | null>
  enabled?: boolean
}

/** `GET /documents`, paginated; the opaque cursor is carried, never parsed. */
export function useDocumentsList(personId: string | null, options: DocumentsQueryOptions) {
  const { context, refreshAuth, enabled = true } = options
  return useInfiniteQuery({
    queryKey: documentsKeys.list(context.clanId, personId),
    queryFn: ({ pageParam, signal }) =>
      listDocuments(
        { cursor: pageParam, person_id: personId ?? undefined },
        { context, refreshAuth, signal },
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => (lastPage.hasMore ? lastPage.cursor : undefined),
    enabled,
  })
}

/** Sign → PUT to Storage → confirm. Every documents list of the clan is invalidated on success. */
export function useUploadDocument(options: DocumentsQueryOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: UploadDocumentInput) => uploadDocument(input, { context, refreshAuth }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentsKeys.lists(context.clanId) })
    },
  })
}

/** `DELETE /documents/{id}`, a soft delete; the document leaves every list. */
export function useDeleteDocument(options: DocumentsQueryOptions) {
  const { context, refreshAuth } = options
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteDocument(id, { context, refreshAuth }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentsKeys.lists(context.clanId) })
    },
  })
}

/**
 * Reads one document for its short-lived signed URL, at the moment the file is opened. Not a
 * cached query: the URL expires (`presignedUrlExpiresAt`), so each open mints a fresh one.
 */
export function useOpenDocument(options: DocumentsQueryOptions) {
  const { context, refreshAuth } = options
  return useMutation({
    mutationFn: (id: string) => getDocument(id, { context, refreshAuth }),
  })
}
