'use client'

import { useTranslations } from 'next-intl'
import { useForm } from 'react-hook-form'
import { useClanSettings, useClanSettingsMutation } from '@/lib/hooks/useAdmin'
import type { ClanSettings } from '@/lib/types'

export default function AdminClanPage() {
  const t = useTranslations('admin')
  const { data: clan, isLoading } = useClanSettings()
  const updateMutation = useClanSettingsMutation()

  const { register, handleSubmit, formState: { isSubmitting } } = useForm<ClanSettings>({
    values: clan,
  })

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-serif text-2xl text-gray-800">{t('clan_settings')}</h1>

      <form
        onSubmit={handleSubmit((data) => updateMutation.mutateAsync(data))}
        className="bg-white rounded-2xl border border-gray-100 shadow-xs p-6 space-y-4"
      >
        {isLoading && (
          <p className="text-sm text-gray-400">Loading...</p>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('clan_name')}</label>
          <input
            {...register('name', { required: true })}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('description')}</label>
          <textarea
            rows={3}
            {...register('description')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2 resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('founding_year')}</label>
            <input
              type="number"
              {...register('founded_year', { valueAsNumber: true })}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('origin_location')}</label>
            <input
              {...register('origin_place')}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={isSubmitting || updateMutation.isPending}
          className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary-hover disabled:opacity-50 transition-colors"
        >
          {isSubmitting || updateMutation.isPending ? t('saving') : t('save_changes')}
        </button>
      </form>
    </div>
  )
}
