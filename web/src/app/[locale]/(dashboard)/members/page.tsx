import { getTranslations } from 'next-intl/server'
import Link from 'next/link'
import { Plus } from 'lucide-react'
import { MemberList } from '@/components/members/MemberList'
import { MemberSearch } from '@/components/members/MemberSearch'
import { getServerAuthContext } from '@/lib/server/auth-context'

export default async function MembersPage() {
  const t = await getTranslations('members')
  const authContext = await getServerAuthContext()
  const canCreateMembers =
    authContext?.currentClanRole === 'editor' || authContext?.currentClanRole === 'admin'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-2xl text-gray-800">{t('page_title')}</h1>
        {canCreateMembers && (
          <Link
            href="./new"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            {t('add_member')}
          </Link>
        )}
      </div>

      <MemberSearch />

      <div className="mt-2">
        <MemberList />
      </div>
    </div>
  )
}
