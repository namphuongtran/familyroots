import { getTranslations } from 'next-intl/server'
import { DocumentUpload } from '@/components/documents/DocumentUpload'
import { DocumentGallery } from '@/components/documents/DocumentGallery'

export default async function DocumentsPage() {
  const t = await getTranslations('documents')

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="font-serif text-2xl text-gray-800">{t('page_title')}</h1>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">{t('upload_section')}</h2>
        <DocumentUpload />
      </div>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 space-y-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">{t('all_documents')}</h2>
        <DocumentGallery />
      </div>
    </div>
  )
}
