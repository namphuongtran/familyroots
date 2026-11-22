'use client'

import { useTranslations } from 'next-intl'
import { useForm } from 'react-hook-form'
import type { ClanProfile, ClanProfileUpdate } from '@/domain/clan/clan-profile'
import { useClientRequestContext } from '@/shared/http/context.client'
import { useClanProfile, useUpdateClanProfile } from '../hooks/use-admin-queries'

/** The four fields this form edits, of the eight `PATCH /clans/me` accepts. */
interface ClanProfileFormValues {
  name: string
  description: string
  foundedYear: number | null
  originPlace: string
}

function toFormValues(profile: ClanProfile): ClanProfileFormValues {
  return {
    name: profile.name,
    description: profile.description ?? '',
    foundedYear: profile.foundedYear,
    originPlace: profile.originPlace ?? '',
  }
}

/**
 * Only the edited fields are sent. The legacy form sent the whole row back, `id`, `slug` and the
 * timestamps included, which the contract refuses with `422 field_not_updatable`. An emptied text
 * field is sent as `null`, and so is an emptied year (`valueAsNumber` reads it as `NaN`).
 */
function toUpdate(values: ClanProfileFormValues): ClanProfileUpdate {
  const year = values.foundedYear
  return {
    name: values.name,
    description: values.description.trim() === '' ? null : values.description,
    foundedYear: year === null || Number.isNaN(year) ? null : year,
    originPlace: values.originPlace.trim() === '' ? null : values.originPlace,
  }
}

/** The clan profile form: the clan's own row, `GET`/`PATCH /clans/me`. */
export function ClanProfileScreen() {
  const t = useTranslations('admin')
  const tCommon = useTranslations('common')
  const request = useClientRequestContext()
  const options = { context: request.context, refreshAuth: request.refreshAuth }
  const profile = useClanProfile({ ...options, enabled: request.ready })
  const updateMutation = useUpdateClanProfile(options)

  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<ClanProfileFormValues>({
    values: profile.data ? toFormValues(profile.data) : undefined,
  })

  const isLoading = !request.ready || profile.isPending

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-foreground font-serif text-2xl">{t('clan_settings')}</h1>

      <form
        onSubmit={handleSubmit((values) => updateMutation.mutateAsync(toUpdate(values)))}
        className="border-border bg-card space-y-4 rounded-2xl border p-6 shadow-xs"
      >
        {isLoading && <p className="text-muted-foreground text-sm">{tCommon('loading')}</p>}
        <div>
          <label className="text-foreground mb-1 block text-sm font-medium">{t('clan_name')}</label>
          <input
            {...register('name', { required: true })}
            className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
          />
        </div>

        <div>
          <label className="text-foreground mb-1 block text-sm font-medium">
            {t('description')}
          </label>
          <textarea
            rows={3}
            {...register('description')}
            className="focus:ring-ring border-input w-full resize-none rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-foreground mb-1 block text-sm font-medium">
              {t('founding_year')}
            </label>
            <input
              type="number"
              {...register('foundedYear', { valueAsNumber: true })}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
            />
          </div>
          <div>
            <label className="text-foreground mb-1 block text-sm font-medium">
              {t('origin_location')}
            </label>
            <input
              {...register('originPlace')}
              className="focus:ring-ring border-input w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-hidden"
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
