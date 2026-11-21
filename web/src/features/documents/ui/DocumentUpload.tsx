'use client'

import { useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { FileText, Upload, X } from 'lucide-react'
import {
  APPROVED_UPLOAD_TYPES,
  exceedsUploadLimit,
  MAX_UPLOAD_MB,
} from '@/domain/document/document'
import type { ClientRequestContext } from '@/shared/http/context.client'
import { cn } from '@/lib/utils/cn'
import { useUploadDocument } from '../hooks/use-documents-queries'

const ACCEPT = APPROVED_UPLOAD_TYPES.join(',')

interface DocumentUploadProps {
  request: ClientRequestContext
}

/**
 * The upload panel (ADR-068): pick or drop one file, name it, upload. A file over the limit is
 * refused here, before any request, with the limit named; the transport refuses it too, so the
 * two cannot disagree. Only rendered for a role that may upload (`DocumentsScreen`).
 */
export function DocumentUpload({ request }: DocumentUploadProps) {
  const t = useTranslations('documents')
  const upload = useUploadDocument({ context: request.context, refreshAuth: request.refreshAuth })
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleFile = (file: File) => {
    upload.reset()
    if (exceedsUploadLimit(file.size)) {
      setError(t('file_too_large', { max: MAX_UPLOAD_MB }))
      setSelectedFile(null)
      return
    }
    setError(null)
    setSelectedFile(file)
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return
    upload.mutate(
      { file: selectedFile, title, documentType: 'other' },
      {
        onSuccess: () => {
          setSelectedFile(null)
          setTitle('')
          if (inputRef.current) inputRef.current.value = ''
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <label
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsDragging(false)
          const file = e.dataTransfer.files[0]
          if (file) handleFile(file)
        }}
        className={cn(
          'focus-within:ring-ring flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-8 transition-colors focus-within:ring-2',
          isDragging ? 'border-primary bg-primary-container' : 'border-border hover:border-input',
        )}
      >
        <Upload className="text-muted-foreground h-8 w-8" aria-hidden />
        <span className="text-muted-foreground text-sm">{t('drop_hint')}</span>
        <span className="text-muted-foreground text-xs">
          {t('allowed_types', { max: MAX_UPLOAD_MB })}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          aria-label={t('choose_file')}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) handleFile(f)
          }}
        />
      </label>

      {error && (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}

      {selectedFile && (
        <>
          <div className="border-border bg-muted flex items-center gap-2 rounded-lg border p-2">
            <FileText className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
            <span className="text-muted-foreground flex-1 truncate text-xs">
              {selectedFile.name}
            </span>
            <button
              type="button"
              aria-label={t('remove_file')}
              onClick={() => setSelectedFile(null)}
            >
              <X className="text-muted-foreground h-3.5 w-3.5" aria-hidden />
            </button>
          </div>
          <div>
            <label
              htmlFor="document-title"
              className="text-foreground mb-1 block text-xs font-medium"
            >
              {t('title')}
            </label>
            <input
              id="document-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={255}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-1.5 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>
          <button
            type="submit"
            disabled={upload.isPending}
            className="bg-primary text-primary-foreground hover:bg-primary-hover w-full rounded-md py-2 text-sm transition-colors disabled:opacity-50"
          >
            {upload.isPending ? t('uploading') : t('upload')}
          </button>
        </>
      )}

      {upload.isError && (
        <p role="alert" className="text-destructive text-xs">
          {t('upload_failed')}
        </p>
      )}
    </form>
  )
}
