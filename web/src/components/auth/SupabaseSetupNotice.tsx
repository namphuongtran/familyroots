'use client'

import { useTranslations } from 'next-intl'
import { isSupabaseConfigured } from '@/lib/supabase/config'

export function SupabaseSetupNotice() {
  const t = useTranslations('auth')

  if (isSupabaseConfigured()) {
    return null
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <p className="font-medium">{t('missing_supabase_config_title')}</p>
      <p className="mt-1 text-amber-800">{t('missing_supabase_config_hint')}</p>
    </div>
  )
}
