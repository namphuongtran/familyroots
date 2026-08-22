'use client'

import { useTranslations } from 'next-intl'
import { useForm } from 'react-hook-form'
import { useClanSettings, useClanSettingsMutation } from '@/lib/hooks/useAdmin'
import type { ClanSettings } from '@/lib/types'

export default function AdminClanPage() {
  const t = useTranslations('admin')
  const { data: clan, isLoading } = useClanSettings()
  const updateMutation = useClanSettingsMutation()

  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<ClanSettings>({
    values: clan,
  })

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-serif text-2xl text-gray-800">{t('clan_settings')}</h1>

      <form
        onSubmit={handleSubmit((data) => updateMutation.mutateAsync(data))}
        className="space-y-4 rounded-2xl border border-gray-100 bg-white p-6 shadow-xs"
      >
        {isLoading && <p className="text-sm text-gray-400">Loading...</p>}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t('clan_name')}</label>
          <input
            {...register('name', { required: true })}
            className="focus:ring-ring w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t('description')}</label>
          <textarea
            rows={3}
            {...register('description')}
            className="focus:ring-ring w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {t('founding_year')}
            </label>
            <input
              type="number"
              {...register('founded_year', { valueAsNumber: true })}
              className="focus:ring-ring w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              {t('origin_location')}
            </label>
            <input
              {...register('origin_place')}
              className="focus:ring-ring w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={isSubmitting || updateMutation.isPending}
          className="bg-primary text-primary-foreground hover:bg-primary-hover rounded-lg px-4 py-2 text-sm transition-colors disabled:opacity-50"
        >
          {isSubmitting || updateMutation.isPending ? t('saving') : t('save_changes')}
        </button>
      </form>
    </div>
  )
}
