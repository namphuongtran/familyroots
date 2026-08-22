import { getTranslations } from 'next-intl/server'
import { DocumentUpload } from '@/components/documents/DocumentUpload'
import { DocumentGallery } from '@/components/documents/DocumentGallery'

export default async function DocumentsPage() {
  const t = await getTranslations('documents')

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="font-serif text-2xl text-gray-800">{t('page_title')}</h1>

      <div className="space-y-3 rounded-2xl border border-gray-100 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase">
          {t('upload_section')}
        </h2>
        <DocumentUpload />
      </div>

      <div className="space-y-3 rounded-2xl border border-gray-100 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase">
          {t('all_documents')}
        </h2>
        <DocumentGallery />
      </div>
    </div>
  )
}
