import { getTranslations } from 'next-intl/server'
import { DocumentUpload } from '@/components/documents/DocumentUpload'
import { DocumentGallery } from '@/components/documents/DocumentGallery'

export default async function DocumentsPage() {
  const t = await getTranslations('documents')

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-foreground font-serif text-2xl">{t('page_title')}</h1>

      <div className="border-border bg-card space-y-3 rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
          {t('upload_section')}
        </h2>
        <DocumentUpload />
      </div>

      <div className="border-border bg-card space-y-3 rounded-2xl border p-5 shadow-xs">
        <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
          {t('all_documents')}
        </h2>
        <DocumentGallery />
      </div>
    </div>
  )
}
