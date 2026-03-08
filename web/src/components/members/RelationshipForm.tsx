'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslations } from 'next-intl'
import {
  marriageSchema,
  type MarriageFormValues,
  parentChildSchema,
  type ParentChildFormValues,
} from '@/lib/validations/relationship.schema'
import { useMarriageMutations, useParentChildMutations } from '@/lib/hooks/useRelationships'
import { MARRIAGE_STATUS_OPTIONS, PARENT_CHILD_TYPE_OPTIONS } from '@/lib/types/relationship'

interface MarriageFormProps {
  personId: string
  onSuccess?: () => void
  onCancel?: () => void
}

export function MarriageForm({ personId, onSuccess, onCancel }: MarriageFormProps) {
  const t = useTranslations('relationship_form')
  const { create } = useMarriageMutations(personId)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<MarriageFormValues>({
    resolver: zodResolver(marriageSchema),
    defaultValues: { person1_id: personId, status: 'married' },
  })

  const onSubmit = async (data: MarriageFormValues) => {
    await create.mutateAsync(data)
    onSuccess?.()
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <input type="hidden" {...register('person1_id')} />

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('spouse_id')} *
        </label>
        <input
          {...register('person2_id')}
          placeholder={t('spouse_id_placeholder')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        {errors.person2_id && (
          <p className="text-xs text-red-500 mt-1">{errors.person2_id.message}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('marriage_status')}
        </label>
        <select
          {...register('status')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          {MARRIAGE_STATUS_OPTIONS.map(s => (
            <option key={s} value={s}>{t(`status.${s}`)}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('marriage_date')}</label>
          <input type="date" {...register('marriage_date')} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('divorce_date')}</label>
          <input type="date" {...register('divorce_date')} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
        </div>
      </div>

      <div className="flex items-center justify-end gap-3 pt-2">
        {onCancel && (
          <button type="button" onClick={onCancel} className="px-4 py-2 text-sm rounded-md border border-gray-300 hover:bg-gray-50 transition-colors">
            {t('cancel')}
          </button>
        )}
        <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm rounded-md bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {isSubmitting ? t('saving') : t('create_marriage')}
        </button>
      </div>
    </form>
  )
}

interface ParentChildFormProps {
  personId: string
  role: 'parent' | 'child'
  onSuccess?: () => void
  onCancel?: () => void
}

export function ParentChildForm({ personId, role, onSuccess, onCancel }: ParentChildFormProps) {
  const t = useTranslations('relationship_form')
  const { create } = useParentChildMutations(personId)

  const defaultValues: Partial<ParentChildFormValues> =
    role === 'parent'
      ? { parent_id: personId, relationship_type: 'biological' }
      : { child_id: personId, relationship_type: 'biological' }

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ParentChildFormValues>({
    resolver: zodResolver(parentChildSchema),
    defaultValues,
  })

  const onSubmit = async (data: ParentChildFormValues) => {
    await create.mutateAsync(data)
    onSuccess?.()
  }

  const otherIdField = role === 'parent' ? 'child_id' : 'parent_id'

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {role === 'parent' && <input type="hidden" {...register('parent_id')} />}
      {role === 'child' && <input type="hidden" {...register('child_id')} />}

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {role === 'parent' ? t('child_id') : t('parent_id')} *
        </label>
        <input
          {...register(otherIdField)}
          placeholder={t(`${otherIdField}_placeholder`)}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        {errors[otherIdField] && (
          <p className="text-xs text-red-500 mt-1">{errors[otherIdField]?.message}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('relationship_type')}
        </label>
        <select
          {...register('relationship_type')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          {PARENT_CHILD_TYPE_OPTIONS.map(opt => (
            <option key={opt} value={opt}>{t(`type.${opt}`)}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center justify-end gap-3 pt-2">
        {onCancel && (
          <button type="button" onClick={onCancel} className="px-4 py-2 text-sm rounded-md border border-gray-300 hover:bg-gray-50 transition-colors">
            {t('cancel')}
          </button>
        )}
        <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm rounded-md bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {isSubmitting ? t('saving') : t('create_relationship')}
        </button>
      </div>
    </form>
  )
}
