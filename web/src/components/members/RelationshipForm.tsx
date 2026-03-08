'use client'

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslations } from 'next-intl'
import { relationshipSchema, type RelationshipFormValues } from '@/lib/validations/relationship.schema'
import { useRelationshipMutations } from '@/lib/hooks/useRelationships'
import { REL_SUBTYPE_OPTIONS, type RelationSubtype } from '@/lib/types/relationship'

interface RelationshipFormProps {
  fromMemberId: string
  onSuccess?: () => void
  onCancel?: () => void
}

export function RelationshipForm({ fromMemberId, onSuccess, onCancel }: RelationshipFormProps) {
  const t = useTranslations('relationship_form')
  const { create: createRelationship } = useRelationshipMutations(fromMemberId)

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RelationshipFormValues>({
    resolver: zodResolver(relationshipSchema),
    defaultValues: { member_id: fromMemberId, is_primary: true },
  })

  const relType = watch('relation_type')

  const subtypeOptions = REL_SUBTYPE_OPTIONS[relType as keyof typeof REL_SUBTYPE_OPTIONS] ?? []

  const onSubmit = async (data: RelationshipFormValues) => {
    await createRelationship.mutateAsync({
      ...data,
      relation_subtype: data.relation_subtype as RelationSubtype,
    })
    onSuccess?.()
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <input type="hidden" {...register('member_id')} />

      {/* To member */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('related_id')} *
        </label>
        <input
          {...register('related_id')}
          placeholder={t('related_id_placeholder')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        {errors.related_id && (
          <p className="text-xs text-red-500 mt-1">{errors.related_id.message}</p>
        )}
      </div>

      {/* Relation type */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('relation_type')} *
        </label>
        <select
          {...register('relation_type')}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{t('select_type')}</option>
          <option value="parent">{t('parent')}</option>
          <option value="child">{t('child')}</option>
          <option value="spouse">{t('spouse')}</option>
        </select>
        {errors.relation_type && (
          <p className="text-xs text-red-500 mt-1">{errors.relation_type.message}</p>
        )}
      </div>

      {/* Subtype — conditional */}
      {subtypeOptions.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('relation_subtype')}
          </label>
          <select
            {...register('relation_subtype')}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">{t('none')}</option>
            {subtypeOptions.map(opt => (
              <option key={opt} value={opt}>
                {t(`subtype.${opt}`)}
              </option>
            ))}
          </select>
        </div>
      )}

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
          {isSubmitting ? t('saving') : t('create_relationship')}
        </button>
      </div>
    </form>
  )
}
