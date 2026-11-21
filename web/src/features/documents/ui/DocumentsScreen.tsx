'use client'

import { useTranslations } from 'next-intl'
import { useCapabilities } from '@/features/auth'
import { useClientRequestContext } from '@/shared/http/context.client'
import { DocumentGallery } from './DocumentGallery'
import { DocumentUpload } from './DocumentUpload'

/**
 * The documents page: upload, then the clan's gallery. What a role sees is rbac.md's line,
 * through `useCapabilities()`: admin and editor upload, only admin deletes, a viewer reads.
 */
export function DocumentsScreen() {
  const t = useTranslations('documents')
  const capabilities = useCapabilities()
  const request = useClientRequestContext()

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-foreground font-serif text-2xl">{t('page_title')}</h1>

      <section className="border-border bg-card space-y-3 rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
          {t('upload_section')}
        </h2>
        {capabilities.uploadDocument ? (
          <DocumentUpload request={request} />
        ) : (
          <p className="text-muted-foreground text-sm">{t('no_upload_permission')}</p>
        )}
      </section>

      <section className="border-border bg-card space-y-3 rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
          {t('all_documents')}
        </h2>
        <DocumentGallery request={request} canDelete={capabilities.deleteDocument} />
      </section>
    </div>
  )
}
