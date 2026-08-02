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

  const documents = data?.pages.flatMap(p => p.data) ?? []

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
      <div className="text-center py-10 text-gray-400">
        <FileText className="h-8 w-8 mx-auto mb-2 opacity-40" />
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
      {documents.map(doc => (
        <div
          key={doc.id}
          className="relative group rounded-xl overflow-hidden border border-gray-200 bg-gray-50 aspect-square flex items-center justify-center"
        >
          <div className="flex flex-col items-center gap-1 p-3">
            <FileText className="h-8 w-8 text-gray-400" />
            <p className="text-[10px] text-center text-gray-500 line-clamp-2">{doc.title}</p>
            <p className="text-[9px] uppercase text-gray-400">{doc.document_type}</p>
            <p className="text-[9px] text-gray-400">{formatDate(doc.created_at)}</p>
            <button
              type="button"
              onClick={() => handleOpen(doc.id)}
              disabled={openingId === doc.id}
              className="mt-1 inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-[10px] text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <ExternalLink className="h-3 w-3" />
              <span>{openingId === doc.id ? 'Opening...' : 'Open'}</span>
            </button>
          </div>

          {canDeleteDocuments && (
            <div className="absolute inset-x-0 bottom-0 flex justify-end bg-linear-to-t from-black/40 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
              {confirmDeleteId === doc.id ? (
                <button
                  onClick={() => { deleteDocument.mutate(doc.id); setConfirmDeleteId(null) }}
                  className="p-1.5 rounded-full bg-red-500 text-white hover:bg-red-600"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  onClick={() => setConfirmDeleteId(doc.id)}
                  className="p-1.5 rounded-full bg-white/80 hover:bg-white text-red-500"
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
