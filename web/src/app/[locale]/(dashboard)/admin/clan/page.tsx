'use client'

import { useTranslations } from 'next-intl'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import api from '@/lib/api/axios'

interface ClanSettings {
  name: string
  description?: string
  founding_year?: number
  origin_location?: string
}

export default function AdminClanPage() {
  const t = useTranslations('admin')
  const qc = useQueryClient()

  const { data: clan, isLoading } = useQuery({
    queryKey: ['clan', 'settings'],
    queryFn: async () => {
      const res = await api.get<ClanSettings>('/clans/me')
      return res.data
    },
  })

  const { register, handleSubmit, formState: { isSubmitting } } = useForm<ClanSettings>({
    values: clan,
  })

  const updateMutation = useMutation({
    mutationFn: (data: ClanSettings) => api.patch('/clans/me', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clan', 'settings'] }),
  })

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-serif text-2xl text-gray-800">{t('clan_settings')}</h1>

      <form
        onSubmit={handleSubmit(data => updateMutation.mutateAsync(data))}
        className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 space-y-4"
      >
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('clan_name')}</label>
          <input
            {...register('name', { required: true })}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('description')}</label>
          <textarea
            rows={3}
            {...register('description')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('founding_year')}</label>
            <input
              type="number"
              {...register('founding_year', { valueAsNumber: true })}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('origin_location')}</label>
            <input
              {...register('origin_location')}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={isSubmitting || updateMutation.isPending}
          className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
        >
          {isSubmitting || updateMutation.isPending ? t('saving') : t('save_changes')}
        </button>
      </form>
    </div>
  )
}
