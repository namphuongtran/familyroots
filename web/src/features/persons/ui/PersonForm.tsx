'use client'

/**
 * Spec §7.7, "Thêm / Sửa người" — the persons create and edit form (S-032).
 * Builds on the S-030 repository/hooks through this feature's own public
 * surface conventions (`../hooks/use-person-mutations`,
 * `../server/persons-repository` for the one-shot refetch a `409` needs —
 * `ui/` may reach its own `server/`, only `ui-does-not-call-transport`
 * (`.dependency-cruiser.cjs`) restricts `api/`).
 *
 * **The part that is easy to skip: `409 stale_write` (ADR-017).** `onSubmit`
 * below never lets that code reach a generic error banner. It refetches the
 * record, diffs it against what the user typed (`stale-write-diff.ts`), and
 * hands the result to `StaleWriteDialog` — spec §7.7c end to end, including
 * the "resubmit 409s again" loop and the 403-mid-edit case
 * (`ForbiddenWriteDialog`).
 *
 * **Scope reductions from spec §7.7, named rather than left silent:**
 * - Fields shown are exactly spec §7.7's own list — Tên gọi, Giới tính, Ngày
 *   sinh, Ngày mất, Nơi chốn, Tiểu sử, Ghi chú. `religion`, `nationality`,
 *   `occupation`, `educationLevel`, `titleRank`, `phone`, and `email` exist
 *   on `Person` but are not in that list, and `phone`/`email` additionally
 *   carry their own ADR-049 role-narrower write rule (a `viewer` may write
 *   them only on their own linked person) that this form does not attempt
 *   to gate. `nationality` is sent as the backend's own default, `'VN'`
 *   (`person-form-schema.ts`'s own comment).
 * - "Chi/nhánh" (spec §7.7's field list) has no home: `Person` carries no
 *   branch field at all — `PersonRow.tsx`'s own comment already recorded
 *   this for the list row, and it is equally true here.
 * - The success/warning "toast" (spec §7.7a/§7.7b) is an inline confirmation
 *   panel replacing the form, not a cross-navigation global toast — no toast
 *   primitive exists anywhere in this codebase yet (`MembersPage`'s own
 *   comment says building one is "exactly the kind of write-UX decision"
 *   a seed should not invent as a side effect of something else), and this
 *   seed is the one that needed to decide, so it decided narrowly: the
 *   confirmation is local to this component, and the caller's `onSuccess`
 *   fires when the user acknowledges it.
 * - The unsaved-changes guard covers the in-form Cancel button and a real
 *   tab close/reload (`beforeunload`), not in-app navigation through the
 *   page shell's own back link — the App Router has no
 *   `routeChangeStart`-equivalent to intercept that without a custom `Link`
 *   wrapper, which is a bigger change than this form owns.
 */

import { useEffect, useState } from 'react'
import { FormProvider, useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslations, useLocale } from 'next-intl'
import type { Person } from '@/domain/person/person'
import type { RequestContext } from '@/shared/http/request-context'
import { ApiError } from '@/shared/http/errors'
import { getPerson } from '../server/persons-repository'
import { useCreatePerson, useUpdatePerson } from '../hooks/use-person-mutations'
import { HistoricalDateField } from './HistoricalDateField'
import { StaleWriteDialog } from './StaleWriteDialog'
import { ForbiddenWriteDialog } from './ForbiddenWriteDialog'
import {
  applyFieldChoice,
  diffPersonFormValues,
  personFormValuesSummary,
  type FieldChoice,
  type FieldDiffRow,
} from './stale-write-diff'
import { defaultDateDisplay } from './date-display-defaults'
import {
  emptyPersonFormValues,
  formValuesToCreateRequest,
  formValuesToUpdateRequest,
  personFormSchema,
  personToFormValues,
  type PersonFormValues,
} from './person-form-schema'

export interface PersonFormProps {
  mode: 'create' | 'edit'
  /** Required, and used, only when `mode === 'edit'`. */
  person?: Person
  context: RequestContext
  onSuccess: (person: Person) => void
  onCancel: () => void
}

interface ConflictState {
  latestPerson: Person
  latestValues: PersonFormValues
  rows: FieldDiffRow[]
  choices: Record<string, FieldChoice>
  repeated: boolean
}

const STALE_WRITE_CODE = 'stale_write'

function encodeOptions(
  t: (key: string, values?: Record<string, string | number>) => string,
  values: PersonFormValues,
) {
  return {
    birthDisplay: defaultDateDisplay(t, values.birthDate),
    deathDisplay: values.hasDied ? defaultDateDisplay(t, values.deathDate) : null,
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return false
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function PersonForm({ mode, person, context, onSuccess, onCancel }: PersonFormProps) {
  const t = useTranslations('member_form')
  const locale = useLocale()

  const [initialValues] = useState<PersonFormValues>(() =>
    mode === 'edit' && person ? personToFormValues(person) : emptyPersonFormValues(),
  )
  /**
   * A plain `useState`, not a `useRef` — the eslint React Compiler rule
   * (`react-hooks/refs`) flags a ref read reachable from `handleSubmit(...)`
   * passed straight into `onSubmit`, because that call runs during render to
   * produce the event handler even though the ref read inside it only
   * happens later, on an actual submit. State avoids the false positive and
   * costs nothing here: every reader of this value is a user-triggered
   * handler that already runs after the render holding the current value
   * has committed.
   */
  const [expectedVersion, setExpectedVersion] = useState<number>(person?.version ?? 1)

  const form = useForm<PersonFormValues>({
    resolver: zodResolver(personFormSchema),
    defaultValues: initialValues,
  })
  const {
    register,
    handleSubmit,
    getValues,
    reset,
    control,
    formState: { errors, isDirty, isSubmitting },
  } = form
  const hasDied = useWatch({ control, name: 'hasDied' })

  const [conflict, setConflict] = useState<ConflictState | null>(null)
  const [forbidden, setForbidden] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [saved, setSaved] = useState<{ person: Person; message: string } | null>(null)

  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      if (!isDirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [isDirty])

  function successMessage(warning: string | null): string {
    return warning ? t('save_success_with_warning', { warning }) : t('save_success')
  }

  async function openConflict(mine: PersonFormValues, repeated: boolean): Promise<void> {
    if (!person) return
    try {
      const latestPerson = await getPerson(person.id, {}, { context })
      const latestValues = personToFormValues(latestPerson)
      const rows = diffPersonFormValues(t, locale, initialValues, mine, latestValues)
      const choices: Record<string, FieldChoice> = {}
      for (const row of rows) choices[row.field] = row.defaultChoice
      setExpectedVersion(latestPerson.version)
      setConflict({ latestPerson, latestValues, rows, choices, repeated })
    } catch {
      setSubmitError(t('network_error_retry'))
    }
  }

  const createMutation = useCreatePerson({ context })
  const updateMutation = useUpdatePerson({ context })

  async function onSubmit(values: PersonFormValues): Promise<void> {
    setSubmitError(null)
    try {
      if (mode === 'create') {
        const { person: created, warning } = await createMutation.mutateAsync(
          formValuesToCreateRequest(values, encodeOptions(t, values)),
        )
        setSaved({ person: created, message: successMessage(warning) })
        return
      }

      if (!person) return
      const body = formValuesToUpdateRequest(values, expectedVersion, encodeOptions(t, values))
      const { person: updated, warning } = await updateMutation.mutateAsync({ id: person.id, body })
      setExpectedVersion(updated.version)
      setSaved({ person: updated, message: successMessage(warning) })
    } catch (error) {
      if (error instanceof ApiError && error.code === STALE_WRITE_CODE) {
        await openConflict(values, false)
        return
      }
      if (error instanceof ApiError && error.status === 403) {
        setForbidden(true)
        return
      }
      setSubmitError(error instanceof ApiError ? error.message : t('network_error_retry'))
    }
  }

  async function handleSaveResolved(): Promise<void> {
    if (!conflict || !person) return
    const merged = structuredClone(getValues())
    for (const row of conflict.rows) {
      if (conflict.choices[row.field] === 'latest') {
        applyFieldChoice(merged, conflict.latestValues, row.field)
      }
    }
    try {
      const body = formValuesToUpdateRequest(merged, expectedVersion, encodeOptions(t, merged))
      const { person: updated, warning } = await updateMutation.mutateAsync({ id: person.id, body })
      setExpectedVersion(updated.version)
      reset(merged)
      setConflict(null)
      setSaved({ person: updated, message: successMessage(warning) })
    } catch (error) {
      if (error instanceof ApiError && error.code === STALE_WRITE_CODE) {
        // Spec §7.7c: "If the resubmit 409s again, reopen the dialog with
        // the newer data" — never auto-resubmit, never retry the stale
        // version, so this goes through the same refetch-and-diff path.
        await openConflict(merged, true)
        return
      }
      reset(merged)
      setConflict(null)
      setSubmitError(error instanceof ApiError ? error.message : t('network_error_retry'))
    }
  }

  function handleDiscardReload(): void {
    if (!conflict) return
    reset(conflict.latestValues)
    setConflict(null)
  }

  async function handleCopyMineFromConflict(): Promise<boolean> {
    return copyToClipboard(personFormValuesSummary(t, locale, getValues()))
  }

  function handleCancelClick(): void {
    if (isDirty && !window.confirm(t('unsaved_changes_confirm'))) return
    onCancel()
  }

  if (saved) {
    return (
      <div className="bg-card space-y-4 rounded-2xl p-6 text-center">
        <p role="status" className="text-foreground text-sm font-medium">
          {saved.message}
        </p>
        <button
          type="button"
          onClick={() => onSuccess(saved.person)}
          className="bg-primary text-primary-foreground hover:bg-primary-hover rounded-full px-5 py-2 text-sm font-medium transition-colors"
        >
          {t('continue_label')}
        </button>
      </div>
    )
  }

  const genderOptions: Array<{ value: PersonFormValues['gender']; label: string }> = [
    { value: 'male', label: t('male') },
    { value: 'female', label: t('female') },
    { value: 'unknown', label: t('unknown') },
  ]

  return (
    <FormProvider {...form}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6 pb-24">
        <section className="space-y-3">
          <h2 className="text-foreground text-sm font-semibold">{t('section_names')}</h2>
          <div>
            <label htmlFor="fullName" className="text-foreground mb-1 block text-sm font-medium">
              {t('full_name')} <span aria-hidden="true">*</span>
            </label>
            <input
              id="fullName"
              type="text"
              aria-required="true"
              aria-invalid={errors.fullName ? true : undefined}
              {...register('fullName')}
              className="border-input bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
            />
            {errors.fullName && (
              <p className="text-destructive mt-1 text-xs">{t('error_full_name_required')}</p>
            )}
          </div>

          <details className="group">
            <summary className="text-primary cursor-pointer text-sm font-medium">
              {t('section_names_other')}
            </summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {(
                [
                  ['birthName', 'birth_name'],
                  ['courtesyName', 'courtesy_name'],
                  ['posthumousName', 'posthumous_name'],
                  ['aliasName', 'alias_name'],
                ] as const
              ).map(([field, labelKey]) => (
                <div key={field}>
                  <label htmlFor={field} className="text-foreground mb-1 block text-sm font-medium">
                    {t(labelKey)}
                  </label>
                  <input
                    id={field}
                    type="text"
                    {...register(field)}
                    className="border-input bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
                  />
                </div>
              ))}
            </div>
          </details>
        </section>

        <section className="space-y-2">
          <h2 className="text-foreground text-sm font-semibold">{t('section_gender')}</h2>
          <div role="radiogroup" aria-label={t('section_gender')} className="flex gap-2">
            {genderOptions.map((option) => (
              <label
                key={option.value}
                className="border-input has-[:checked]:bg-primary has-[:checked]:text-primary-foreground has-[:checked]:border-primary text-foreground flex cursor-pointer items-center rounded-full border px-4 py-2 text-sm transition-colors"
              >
                <input
                  type="radio"
                  value={option.value}
                  {...register('gender')}
                  className="sr-only"
                />
                {option.label}
              </label>
            ))}
          </div>
        </section>

        <section className="space-y-2">
          <h2 className="text-foreground text-sm font-semibold">{t('section_birth')}</h2>
          <HistoricalDateField namePrefix="birthDate" idBase="birth" />
        </section>

        <section className="space-y-2">
          <label className="text-foreground flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" {...register('hasDied')} className="rounded" />
            {t('has_died')}
          </label>
          {hasDied && <HistoricalDateField namePrefix="deathDate" idBase="death" />}
        </section>

        <section className="space-y-3">
          <h2 className="text-foreground text-sm font-semibold">{t('section_places')}</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ['birthPlace', 'birth_place'],
                ['deathPlace', 'death_place'],
                ['burialPlace', 'burial_place'],
                ['tombLocation', 'tomb_location'],
                ['residencePlace', 'residence_place'],
              ] as const
            ).map(([field, labelKey]) => (
              <div key={field}>
                <label htmlFor={field} className="text-foreground mb-1 block text-sm font-medium">
                  {t(labelKey)}
                </label>
                <input
                  id={field}
                  type="text"
                  {...register(field)}
                  className="border-input bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
                />
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-2">
          <label htmlFor="biography" className="text-foreground block text-sm font-semibold">
            {t('section_biography')}
          </label>
          <textarea
            id="biography"
            rows={4}
            {...register('biography')}
            className="border-input bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
          />
        </section>

        <section className="space-y-2">
          <label htmlFor="notes" className="text-foreground block text-sm font-semibold">
            {t('section_notes')}
          </label>
          <textarea
            id="notes"
            rows={3}
            {...register('notes')}
            className="border-input bg-background text-foreground focus:ring-ring w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-offset-2 focus:outline-none"
          />
        </section>

        {submitError && (
          <p role="alert" className="text-destructive text-sm">
            {submitError}
          </p>
        )}

        <div className="bg-card/80 fixed inset-x-0 bottom-0 flex justify-end gap-3 p-4 backdrop-blur-[20px]">
          <button
            type="button"
            onClick={handleCancelClick}
            disabled={isSubmitting}
            className="border-input text-foreground hover:bg-muted rounded-full border px-4 py-2 text-sm transition-colors disabled:opacity-60"
          >
            {t('cancel')}
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-primary text-primary-foreground hover:bg-primary-hover rounded-full px-5 py-2 text-sm font-medium transition-colors disabled:opacity-60"
          >
            {isSubmitting ? t('saving') : submitError ? t('retry') : t('save')}
          </button>
        </div>
      </form>

      <StaleWriteDialog
        open={conflict !== null}
        personName={person?.fullName ?? ''}
        rows={conflict?.rows ?? []}
        repeatedConflict={conflict?.repeated ?? false}
        choices={conflict?.choices ?? {}}
        onChoiceChange={(field, choice) =>
          setConflict((current) =>
            current ? { ...current, choices: { ...current.choices, [field]: choice } } : current,
          )
        }
        onSaveResolved={() => void handleSaveResolved()}
        onDiscardReload={handleDiscardReload}
        onCopyMine={handleCopyMineFromConflict}
        copyText={personFormValuesSummary(t, locale, getValues())}
        saving={updateMutation.isPending}
      />

      <ForbiddenWriteDialog
        open={forbidden}
        onCopyMine={() => copyToClipboard(personFormValuesSummary(t, locale, getValues()))}
        onClose={() => {
          setForbidden(false)
          onCancel()
        }}
      />
    </FormProvider>
  )
}
