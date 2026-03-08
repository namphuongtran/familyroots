'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { FileText, Download, Trash2, Eye } from 'lucide-react'
import { useDocuments, useDocumentMutations } from '@/lib/hooks/useDocuments'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDate } from '@/lib/utils/date'

interface DocumentGalleryProps {
  personId?: string
}

export function DocumentGallery({ personId }: DocumentGalleryProps) {
  const t = useTranslations('documents')
  const { data, isLoading } = useDocuments(personId)
  const { deleteDocument } = useDocumentMutations()
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

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

  const isImage = (url: string) => /\.(jpg|jpeg|png|heic|webp)$/i.test(url)

  return (
    <div className="grid grid-cols-2 gap-2">
      {documents.map(doc => (
        <div
          key={doc.id}
          className="relative group rounded-xl overflow-hidden border border-gray-200 bg-gray-50 aspect-square flex items-center justify-center"
        >
          {isImage(doc.file_url) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={doc.file_url} alt={doc.title} className="w-full h-full object-cover" />
          ) : (
            <div className="flex flex-col items-center gap-1 p-3">
              <FileText className="h-8 w-8 text-gray-400" />
              <p className="text-[10px] text-center text-gray-500 line-clamp-2">{doc.title}</p>
              <p className="text-[9px] text-gray-400">{formatDate(doc.created_at)}</p>
            </div>
          )}

          {/* hover overlay */}
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <a
              href={doc.file_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-full bg-white/80 hover:bg-white text-gray-700"
            >
              <Eye className="h-3.5 w-3.5" />
            </a>
            <a
              href={doc.file_url}
              download
              className="p-1.5 rounded-full bg-white/80 hover:bg-white text-gray-700"
            >
              <Download className="h-3.5 w-3.5" />
            </a>
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
        </div>
      ))}
    </div>
  )
}
