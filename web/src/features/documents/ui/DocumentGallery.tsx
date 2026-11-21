'use client'

import { useState } from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { ExternalLink, FileText, Trash2 } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import type { ClientRequestContext } from '@/shared/http/context.client'
import {
  useDeleteDocument,
  useDocumentsList,
  useOpenDocument,
} from '../hooks/use-documents-queries'

interface DocumentGalleryProps {
  request: ClientRequestContext
  /** Admin only (rbac.md): delete is a soft delete, restorable for the retention window. */
  canDelete: boolean
}

function formatCreatedAt(iso: string, locale: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date)
}

/**
 * The clan's documents. The list carries no URL: the file sits in a private bucket, and "open"
 * reads the document for a short-lived signed URL at that moment (`useOpenDocument`).
 */
export function DocumentGallery({ request, canDelete }: DocumentGalleryProps) {
  const t = useTranslations('documents')
  const tCommon = useTranslations('common')
  const locale = useLocale()
  const options = { context: request.context, refreshAuth: request.refreshAuth }
  const list = useDocumentsList(null, { ...options, enabled: request.ready })
  const remove = useDeleteDocument(options)
  const open = useOpenDocument(options)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  if (!request.ready || list.isPending) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    )
  }

  if (list.isError) {
    return (
      <div className="space-y-2">
        <p className="text-muted-foreground text-sm">{tCommon('error')}</p>
        <button
          type="button"
          onClick={() => void list.refetch()}
          className="text-primary text-sm font-medium underline"
        >
          {tCommon('retry')}
        </button>
      </div>
    )
  }

  const documents = list.data.pages.flatMap((page) => page.items)

  if (documents.length === 0) {
    return (
      <div className="text-muted-foreground py-10 text-center">
        <FileText className="mx-auto mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="text-sm">{t('no_documents')}</p>
      </div>
    )
  }

  const handleOpen = (id: string) => {
    open.mutate(id, {
      onSuccess: (document) => {
        if (document.presignedUrl) {
          window.open(document.presignedUrl, '_blank', 'noopener,noreferrer')
        }
      },
    })
  }

  const openingId = open.isPending ? open.variables : null

  return (
    <div className="space-y-3">
      <ul className="grid grid-cols-2 gap-2">
        {documents.map((doc) => (
          <li
            key={doc.id}
            className="group border-border bg-muted relative flex aspect-square items-center justify-center overflow-hidden rounded-xl border"
          >
            <div className="flex flex-col items-center gap-1 p-3">
              <FileText className="text-muted-foreground h-8 w-8" aria-hidden />
              <p className="text-muted-foreground line-clamp-2 text-center text-[10px]">
                {doc.title}
              </p>
              <p className="text-muted-foreground text-[9px] uppercase">{doc.documentType}</p>
              <p className="text-muted-foreground text-[9px]">
                {formatCreatedAt(doc.createdAt, locale)}
              </p>
              <button
                type="button"
                onClick={() => handleOpen(doc.id)}
                disabled={openingId === doc.id}
                className="border-border bg-card text-muted-foreground hover:bg-muted mt-1 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ExternalLink className="h-3 w-3" aria-hidden />
                <span>{openingId === doc.id ? t('opening') : t('open')}</span>
              </button>
            </div>

            {canDelete && (
              <div className="from-scrim absolute inset-x-0 bottom-0 flex justify-end bg-linear-to-t to-transparent p-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
                {confirmDeleteId === doc.id ? (
                  <button
                    type="button"
                    aria-label={t('confirm_delete', { title: doc.title })}
                    disabled={remove.isPending}
                    onClick={() =>
                      remove.mutate(doc.id, { onSettled: () => setConfirmDeleteId(null) })
                    }
                    className="bg-destructive hover:bg-destructive/90 text-destructive-foreground rounded-full p-1.5"
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                ) : (
                  <button
                    type="button"
                    aria-label={t('delete_document', { title: doc.title })}
                    onClick={() => setConfirmDeleteId(doc.id)}
                    className="text-destructive bg-card/80 hover:bg-card rounded-full p-1.5"
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {open.isError && (
        <p role="alert" className="text-destructive text-xs">
          {tCommon('error')}
        </p>
      )}
      {list.hasNextPage && (
        <button
          type="button"
          onClick={() => void list.fetchNextPage()}
          disabled={list.isFetchingNextPage}
          className="text-primary text-sm font-medium underline disabled:opacity-60"
        >
          {t('load_more')}
        </button>
      )}
    </div>
  )
}
