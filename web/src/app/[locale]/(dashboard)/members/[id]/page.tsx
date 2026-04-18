import { getTranslations } from 'next-intl/server'
import Link from 'next/link'
import { ArrowLeft, Edit } from 'lucide-react'
import { MemberDetailClient } from '@/components/members/MemberDetailClient'
import { getServerAuthContext } from '@/lib/server/auth-context'

export default async function MemberDetailPage({
  params,
}: {
  params: Promise<{ id: string; locale: string }>
}) {
  const { id } = await params
  const t = await getTranslations('member')
  const authContext = await getServerAuthContext()
  const canEditMember =
    authContext?.currentClanRole === 'editor' || authContext?.currentClanRole === 'admin'

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <Link href="../" className="text-gray-400 hover:text-gray-600">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="font-serif text-2xl text-gray-800">{t('profile_title')}</h1>
        {canEditMember && (
          <Link
            href={`./edit`}
            className="ml-auto flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <Edit className="h-3.5 w-3.5" />
            {t('edit')}
          </Link>
        )}
      </div>

      <MemberDetailClient personId={id} />
    </div>
  )
}
