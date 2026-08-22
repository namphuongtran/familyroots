'use client'

import { useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Upload, X, FileText } from 'lucide-react'
import { useCapabilities } from '@/lib/hooks/useCapabilities'
import { useDocumentMutations } from '@/lib/hooks/useDocuments'
import { cn } from '@/lib/utils/cn'

const ACCEPT = '.pdf,.jpg,.jpeg,.png,.heic,.doc,.docx'
const MAX_MB = 20

interface DocumentUploadProps {
  personId?: string
  onSuccess?: () => void
}

export function DocumentUpload({ personId, onSuccess }: DocumentUploadProps) {
  const t = useTranslations('documents')
  const { canUploadDocuments } = useCapabilities()
  const { uploadDocument } = useDocumentMutations()
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleFile = (file: File) => {
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(t('file_too_large', { max: MAX_MB }))
      return
    }
    setError(null)
    setSelectedFile(file)
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile || !canUploadDocuments) return
    await uploadDocument.mutateAsync({ file: selectedFile, title, person_id: personId })
    setSelectedFile(null)
    setTitle('')
    onSuccess?.()
  }

  if (!canUploadDocuments) {
    return <p className="text-sm text-gray-500">You do not have permission to upload documents.</p>
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-8 transition-colors',
          isDragging
            ? 'border-primary bg-primary-container'
            : 'border-gray-200 hover:border-gray-300',
        )}
      >
        <Upload className="h-8 w-8 text-gray-300" />
        <p className="text-sm text-gray-500">{t('drop_hint')}</p>
        <p className="text-xs text-gray-400">{t('allowed_types')}</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) handleFile(f)
          }}
        />
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {selectedFile && (
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-2">
          <FileText className="h-4 w-4 shrink-0 text-gray-400" />
          <span className="flex-1 truncate text-xs text-gray-600">{selectedFile.name}</span>
          <button type="button" onClick={() => setSelectedFile(null)}>
            <X className="h-3.5 w-3.5 text-gray-400" />
          </button>
        </div>
      )}

      {selectedFile && (
        <>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">{t('title')}</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="focus:ring-ring w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>
          <button
            type="submit"
            disabled={uploadDocument.isPending}
            className="bg-primary text-primary-foreground hover:bg-primary-hover w-full rounded-md py-2 text-sm transition-colors disabled:opacity-50"
          >
            {uploadDocument.isPending ? t('uploading') : t('upload')}
          </button>
        </>
      )}
    </form>
  )
}
