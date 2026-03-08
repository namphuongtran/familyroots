'use client'

import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslations } from 'next-intl'
import { memberSchema, type MemberFormValues } from '@/lib/validations/member.schema'
import { useMemberMutations } from '@/lib/hooks/useMembers'
import type { Member } from '@/lib/types'

interface MemberFormProps {
  member?: Member
  onSuccess?: (id: string) => void
  onCancel?: () => void
}

export function MemberForm({ member, onSuccess, onCancel }: MemberFormProps) {
  const t = useTranslations('member_form')
  const isEdit = !!member?.id
  const { create, update } = useMemberMutations()
  const createMember = create
  const updateMember = update

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MemberFormValues>({
    resolver: zodResolver(memberSchema),
    defaultValues: member
      ? {
          full_name: member.full_name,
          gender: member.gender,
          birth_date: member.birth_date ?? '',
          death_date: member.death_date ?? '',
          birth_date_approx: member.birth_date_approx ?? false,
          death_date_approx: member.death_date_approx ?? false,
          birth_place: member.birth_place ?? '',
          death_place: member.death_place ?? '',
          notes: member.notes ?? '',
          generation: member.generation ?? undefined,
        }
      : { birth_date_approx: false, death_date_approx: false },
  })

  useEffect(() => {
    if (member) reset({ ...member })
  }, [member, reset])

  const onSubmit = async (data: MemberFormValues) => {
    if (isEdit) {
      await updateMember.mutateAsync({ id: member!.id, ...data })
      onSuccess?.(member!.id)
    } else {
      const created = await createMember.mutateAsync(data)
      onSuccess?.(created.id)
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      {/* Full Name */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('full_name')} *
        </label>
        <input
          {...register('full_name')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          placeholder={t('full_name_placeholder')}
        />
        {errors.full_name && (
          <p className="text-xs text-red-500 mt-1">{errors.full_name.message}</p>
        )}
      </div>

      {/* Gender */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('gender')} *
        </label>
        <select
          {...register('gender')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{t('select_gender')}</option>
          <option value="male">{t('male')}</option>
          <option value="female">{t('female')}</option>
          <option value="unknown">{t('unknown')}</option>
        </select>
        {errors.gender && (
          <p className="text-xs text-red-500 mt-1">{errors.gender.message}</p>
        )}
      </div>

      {/* Birth Date */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('birth_date')}
          </label>
          <input
            type="date"
            {...register('birth_date')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          {errors.birth_date && (
            <p className="text-xs text-red-500 mt-1">{errors.birth_date.message}</p>
          )}
        </div>
        <div className="flex items-end pb-2">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" {...register('birth_date_approx')} className="rounded" />
            {t('approx')}
          </label>
        </div>
      </div>

      {/* Death Date */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('death_date')}
          </label>
          <input
            type="date"
            {...register('death_date')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          {errors.death_date && (
            <p className="text-xs text-red-500 mt-1">{errors.death_date.message}</p>
          )}
        </div>
        <div className="flex items-end pb-2">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" {...register('death_date_approx')} className="rounded" />
            {t('approx')}
          </label>
        </div>
      </div>

      {/* Birth / Death Place */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('birth_place')}
          </label>
          <input
            {...register('birth_place')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('death_place')}
          </label>
          <input
            {...register('death_place')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
      </div>

      {/* Generation */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('generation')}
        </label>
        <input
          type="number"
          min={1}
          {...register('generation', { valueAsNumber: true })}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      {/* Notes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('notes')}
        </label>
        <textarea
          rows={3}
          {...register('notes')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-2">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-md border border-gray-300 hover:bg-gray-50 transition-colors"
          >
            {t('cancel')}
          </button>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="px-4 py-2 text-sm rounded-md bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isSubmitting ? t('saving') : isEdit ? t('save_changes') : t('create_member')}
        </button>
      </div>
    </form>
  )
}
