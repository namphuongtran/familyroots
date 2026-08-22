'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ExternalLink, FileText, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { getDocument } from '@/application/documents/use-cases/document-queries'
import { documentQueryRepository } from '@/infrastructure/documents/document-query-repository'
import { useCapabilities } from '@/lib/hooks/useCapabilities'
import { documentKeys, useDocuments, useDocumentMutations } from '@/lib/hooks/useDocuments'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate } from '@/lib/utils/date'

interface DocumentGalleryProps {
  personId?: string
}

export function DocumentGallery({ personId }: DocumentGalleryProps) {
  const t = useTranslations('documents')
  const { canDeleteDocuments } = useCapabilities()
  const { data, isLoading } = useDocuments(personId)
  const { deleteDocument } = useDocumentMutations()
  const queryClient = useQueryClient()
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [openingId, setOpeningId] = useState<string | null>(null)

  const documents = data?.pages.flatMap((p) => p.data) ?? []

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <div className="text-muted-foreground py-10 text-center">
        <FileText className="mx-auto mb-2 h-8 w-8 opacity-40" />
        <p className="text-sm">{t('no_documents')}</p>
      </div>
    )
  }

  const handleOpen = async (id: string) => {
    try {
      setOpeningId(id)
      const document = await queryClient.fetchQuery({
        queryKey: documentKeys.detail(id),
        queryFn: () => getDocument(documentQueryRepository, id),
        staleTime: 60_000,
      })

      if (document.presigned_url) {
        window.open(document.presigned_url, '_blank', 'noopener,noreferrer')
      }
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className="group border-border bg-muted relative flex aspect-square items-center justify-center overflow-hidden rounded-xl border"
        >
          <div className="flex flex-col items-center gap-1 p-3">
            <FileText className="text-muted-foreground h-8 w-8" />
            <p className="text-muted-foreground line-clamp-2 text-center text-[10px]">
              {doc.title}
            </p>
            <p className="text-muted-foreground text-[9px] uppercase">{doc.document_type}</p>
            <p className="text-muted-foreground text-[9px]">{formatDate(doc.created_at)}</p>
            <button
              type="button"
              onClick={() => handleOpen(doc.id)}
              disabled={openingId === doc.id}
              className="border-border bg-card text-muted-foreground hover:bg-muted mt-1 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ExternalLink className="h-3 w-3" />
              <span>{openingId === doc.id ? 'Opening...' : 'Open'}</span>
            </button>
          </div>

          {canDeleteDocuments && (
            <div className="absolute inset-x-0 bottom-0 flex justify-end bg-linear-to-t from-black/40 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
              {confirmDeleteId === doc.id ? (
                <button
                  onClick={() => {
                    deleteDocument.mutate(doc.id)
                    setConfirmDeleteId(null)
                  }}
                  className="bg-destructive hover:bg-destructive/90 rounded-full p-1.5 text-white"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  onClick={() => setConfirmDeleteId(doc.id)}
                  className="text-destructive rounded-full bg-white/80 p-1.5 hover:bg-white"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
