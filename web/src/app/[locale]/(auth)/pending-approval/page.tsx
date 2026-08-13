'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useAuthActions } from '@/lib/hooks/useAuth'

export default function PendingApprovalPage() {
  const t = useTranslations('auth')
  const { signOut } = useAuthActions()

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="max-w-sm w-full text-center bg-white rounded-2xl p-8 shadow-xs border border-gray-100 space-y-3">
        <div className="text-5xl">⏳</div>
        <h2 className="font-serif text-xl text-gray-800">{t('pending_approval')}</h2>
        <p className="text-sm text-gray-500">{t('pending_subtitle')}</p>
        <div className="flex items-center justify-center gap-3 pt-2">
          <Link href="../login" className="text-sm text-primary hover:underline">
            {t('login')}
          </Link>
          <button onClick={signOut} className="text-sm text-gray-500 hover:text-gray-700">
            {t('logout')}
          </button>
        </div>
      </div>
    </div>
  )
}
