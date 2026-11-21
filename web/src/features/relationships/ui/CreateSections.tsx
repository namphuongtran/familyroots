'use client'

import { useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import type { Marriage } from '@/domain/relationship/relationship'
import type { RequestContext } from '@/shared/http/request-context'
import { useCreatePerson } from '@/features/persons'
import { usePersonMarriages } from '../hooks/use-relationship-queries'
import { useRelatedPeople } from '../hooks/use-related-people'
import { useCreateMarriage, useCreateParentChild } from '../hooks/use-relationship-mutations'
import { PersonPicker, type PickedPerson } from './PersonPicker'
import { fieldClass, primaryButtonClass } from './editor-classes'
import { writeErrorText } from './write-error-text'
import { nextSpouseOrder, parentTooYoungDetail } from './relationship-editor-model'

interface SectionProps {
  readonly personId: string
  readonly context: RequestContext
  readonly refreshAuth?: () => Promise<RequestContext | null>
  readonly ready: boolean
  /** A write succeeded; `warning` is the response's `meta.warning`, if any. */
  readonly onSaved: (warning: string | null) => void
}

type T = ReturnType<typeof useTranslations>

/**
 * A field's error text: `422 relationship.parent_too_young` spelled out from `detail.min_age_gap`
 * and `detail.actual` (spec §7.7a), anything else through `writeErrorText`.
 */
function fieldErrorText(t: T, error: unknown): string {
  const detail = parentTooYoungDetail(error)
  if (detail) {
    return t('error_parent_too_young', { min_age_gap: detail.minAgeGap, actual: detail.actual })
  }
  return writeErrorText(t, error)
}

/** Turns a picked person into an id, creating the inline one first (`POST /persons`). */
function useResolvePicked(context: RequestContext, refreshAuth?: SectionProps['refreshAuth']) {
  const createPerson = useCreatePerson({ context, refreshAuth })
  return async (picked: PickedPerson): Promise<string> => {
    if (picked.kind === 'existing') return picked.id
    const { person } = await createPerson.mutateAsync({
      full_name: picked.fullName.trim(),
      gender: picked.gender,
      birth_date_precision: 'unknown',
      death_date_precision: 'unknown',
      // The backend's own default, as the persons form sends it (`person-form-schema.ts`).
      nationality: 'VN',
    })
    return person.id
  }
}

/** Client-side check before any write: someone picked, and a new person named. */
function pickedError(t: T, picked: PickedPerson | null): string | null {
  if (picked === null) return t('error_pick_person')
  if (picked.kind === 'new' && picked.fullName.trim().length === 0) return t('error_name_required')
  return null
}

/**
 * Add a spouse: pick or create the person, with `spouse_order` prefilled to one past the
 * highest live rank (`nextSpouseOrder`) and editable. `POST /relationships/marriages`.
 */
export function AddSpouseSection({
  personId,
  marriages,
  context,
  refreshAuth,
  ready,
  onSaved,
}: SectionProps & { readonly marriages: readonly Marriage[] }) {
  const t = useTranslations('relationship_editor')
  const resolve = useResolvePicked(context, refreshAuth)
  const create = useCreateMarriage({ context, refreshAuth })
  const [picked, setPicked] = useState<PickedPerson | null>(null)
  const [orderInput, setOrderInput] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [orderError, setOrderError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const order = orderInput ?? String(nextSpouseOrder(marriages))
  const excludeIds = useMemo(
    () => [
      personId,
      ...marriages.map((m) => (m.person1Id === personId ? m.person2Id : m.person1Id)),
    ],
    [personId, marriages],
  )

  async function submit() {
    const pickError = pickedError(t, picked)
    const trimmed = order.trim()
    const parsed = Number(trimmed)
    const badOrder = trimmed.length > 0 && (!Number.isInteger(parsed) || parsed < 1)
    setError(pickError)
    setOrderError(badOrder ? t('error_spouse_order') : null)
    if (pickError || badOrder || picked === null) return
    setSaving(true)
    try {
      const spouseId = await resolve(picked)
      // Created once: a retry after a refused link reuses this person rather than making another.
      if (picked.kind === 'new')
        setPicked({ kind: 'existing', id: spouseId, fullName: picked.fullName })
      const { warning } = await create.mutateAsync({
        person1_id: personId,
        person2_id: spouseId,
        status: 'married',
        spouse_order: trimmed.length > 0 ? parsed : null,
        marriage_date_precision: 'unknown',
        divorce_date_precision: 'unknown',
      })
      setPicked(null)
      setOrderInput(null)
      onSaved(warning)
    } catch (e) {
      setError(fieldErrorText(t, e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <PersonPicker
        idBase="add-spouse"
        label={t('spouse')}
        value={picked}
        onChange={setPicked}
        allowCreate
        excludeIds={excludeIds}
        error={error}
        context={context}
        refreshAuth={refreshAuth}
        ready={ready}
      />
      <div>
        <label
          htmlFor="add-spouse-order"
          className="text-foreground mb-1 block text-sm font-semibold"
        >
          {t('spouse_order_label')}
        </label>
        <input
          id="add-spouse-order"
          type="number"
          min={1}
          step={1}
          inputMode="numeric"
          value={order}
          aria-invalid={orderError ? true : undefined}
          onChange={(e) => setOrderInput(e.target.value)}
          className={fieldClass}
        />
        {orderError && <p className="text-destructive mt-1 text-xs">{orderError}</p>}
      </div>
      <button
        type="button"
        onClick={() => void submit()}
        disabled={saving}
        className={primaryButtonClass}
      >
        {saving ? t('saving') : t('save')}
      </button>
    </div>
  )
}

/**
 * Link a father and a mother. The mother is chosen from the father's own marriages, read through
 * `GET /persons/{father}/marriages`, or left empty: a mother who is not one of the father's
 * spouses cannot be picked. Each link is a `POST /relationships/parent-child`; a
 * `parent_too_young` lands under the parent it names.
 */
export function ParentsSection({ personId, context, refreshAuth, ready, onSaved }: SectionProps) {
  const t = useTranslations('relationship_editor')
  const tRel = useTranslations('relationship')
  const create = useCreateParentChild({ context, refreshAuth })
  const [father, setFather] = useState<PickedPerson | null>(null)
  const [motherId, setMotherId] = useState('')
  const [fatherError, setFatherError] = useState<string | null>(null)
  const [motherError, setMotherError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const fatherId = father?.kind === 'existing' ? father.id : ''
  const fatherMarriages = usePersonMarriages(fatherId, { context, refreshAuth, enabled: ready })
  const wifeIds = useMemo(
    () =>
      (fatherMarriages.data ?? []).map((m) =>
        m.person1Id === fatherId ? m.person2Id : m.person1Id,
      ),
    [fatherMarriages.data, fatherId],
  )
  const wives = useRelatedPeople(wifeIds, { context, refreshAuth, enabled: ready })

  async function submit() {
    const pickError = father === null ? t('error_pick_person') : null
    setFatherError(pickError)
    setMotherError(null)
    if (!fatherId) return
    setSaving(true)
    let warning: string | null = null
    try {
      try {
        const result = await create.mutateAsync({
          parent_id: fatherId,
          child_id: personId,
          relationship_type: 'biological',
        })
        warning = result.warning
      } catch (e) {
        setFatherError(fieldErrorText(t, e))
        return
      }
      if (motherId) {
        try {
          const result = await create.mutateAsync({
            parent_id: motherId,
            child_id: personId,
            relationship_type: 'biological',
          })
          warning = [warning, result.warning].filter(Boolean).join(' ') || null
        } catch (e) {
          // The father's link stands. Say so, and put the refusal under the mother.
          setMotherError(fieldErrorText(t, e))
          setFather(null)
          onSaved(warning)
          return
        }
      }
      setFather(null)
      setMotherId('')
      onSaved(warning)
    } finally {
      setSaving(false)
    }
  }

  const motherErrorId = 'link-mother-error'

  return (
    <div className="space-y-4">
      <PersonPicker
        idBase="link-father"
        label={t('father')}
        value={father}
        onChange={(v) => {
          setFather(v)
          setMotherId('')
        }}
        allowCreate={false}
        excludeIds={[personId]}
        error={fatherError}
        context={context}
        refreshAuth={refreshAuth}
        ready={ready}
      />
      <div>
        <label htmlFor="link-mother" className="text-foreground mb-1 block text-sm font-semibold">
          {t('mother')}
        </label>
        <select
          id="link-mother"
          value={motherId}
          disabled={!fatherId}
          aria-invalid={motherError ? true : undefined}
          aria-describedby={motherError ? motherErrorId : undefined}
          onChange={(e) => setMotherId(e.target.value)}
          className={fieldClass}
        >
          <option value="">{t('mother_none')}</option>
          {wifeIds.map((id) => (
            <option key={id} value={id}>
              {wives.get(id)?.fullName ?? tRel('unknown_person')}
            </option>
          ))}
        </select>
        <p className="text-muted-foreground mt-1 text-xs">
          {fatherId ? t('mother_hint') : t('pick_father_first')}
        </p>
        {motherError && (
          <p id={motherErrorId} role="alert" className="text-destructive mt-1 text-sm">
            {motherError}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => void submit()}
        disabled={saving}
        className={primaryButtonClass}
      >
        {saving ? t('saving') : t('save')}
      </button>
    </div>
  )
}

/** Add a child: pick or create the person. `POST /relationships/parent-child`. */
export function AddChildSection({ personId, context, refreshAuth, ready, onSaved }: SectionProps) {
  const t = useTranslations('relationship_editor')
  const resolve = useResolvePicked(context, refreshAuth)
  const create = useCreateParentChild({ context, refreshAuth })
  const [picked, setPicked] = useState<PickedPerson | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    const pickError = pickedError(t, picked)
    setError(pickError)
    if (pickError || picked === null) return
    setSaving(true)
    try {
      const childId = await resolve(picked)
      // Created once: a retry after a refused link reuses this person rather than making another.
      if (picked.kind === 'new')
        setPicked({ kind: 'existing', id: childId, fullName: picked.fullName })
      const { warning } = await create.mutateAsync({
        parent_id: personId,
        child_id: childId,
        relationship_type: 'biological',
      })
      setPicked(null)
      onSaved(warning)
    } catch (e) {
      setError(fieldErrorText(t, e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <PersonPicker
        idBase="add-child"
        label={t('child')}
        value={picked}
        onChange={setPicked}
        allowCreate
        excludeIds={[personId]}
        error={error}
        context={context}
        refreshAuth={refreshAuth}
        ready={ready}
      />
      <button
        type="button"
        onClick={() => void submit()}
        disabled={saving}
        className={primaryButtonClass}
      >
        {saving ? t('saving') : t('save')}
      </button>
    </div>
  )
}
