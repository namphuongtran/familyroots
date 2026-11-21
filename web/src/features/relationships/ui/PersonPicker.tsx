'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import type { Gender } from '@/domain/person/person'
import type { RequestContext } from '@/shared/http/request-context'
import { usePersonSearch } from '@/features/persons'
import { fieldClass } from './editor-classes'

/** What the picker hands back: a person who exists, or the two fields to create one inline. */
export type PickedPerson =
  | { readonly kind: 'existing'; readonly id: string; readonly fullName: string }
  | { readonly kind: 'new'; readonly fullName: string; readonly gender: Gender }

const SEARCH_DEBOUNCE_MS = 250

interface PersonPickerProps {
  /** Unique per picker on screen, so every label pairs with its own input. */
  readonly idBase: string
  readonly label: string
  readonly value: PickedPerson | null
  readonly onChange: (value: PickedPerson | null) => void
  /** Offer "Tạo người mới" (spouse, child). A parent is always someone already recorded. */
  readonly allowCreate: boolean
  /** Ids that cannot be picked: the person being edited, and anyone already linked this way. */
  readonly excludeIds: readonly string[]
  /** Shown under the field, tied to it by `aria-describedby`: the 422 lands here (spec §7.7a). */
  readonly error: string | null
  readonly context: RequestContext
  readonly refreshAuth?: () => Promise<RequestContext | null>
  readonly ready: boolean
}

/**
 * Pick an existing person by name (`GET /persons/search`, through the persons slice), or, where
 * `allowCreate`, type a new one's name and gender for the caller to create on save. The caller
 * creates the person, not the picker, so nothing is written until the editor's save.
 */
export function PersonPicker({
  idBase,
  label,
  value,
  onChange,
  allowCreate,
  excludeIds,
  error,
  context,
  refreshAuth,
  ready,
}: PersonPickerProps) {
  const t = useTranslations('relationship_editor')
  const [text, setText] = useState('')
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const handle = setTimeout(() => setQuery(text.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [text])

  const search = usePersonSearch(
    { q: query, limit: 10 },
    { context, refreshAuth, enabled: ready && value === null && !creating },
  )
  const hits = (search.data ?? []).filter((hit) => !excludeIds.includes(hit.id))
  const errorId = `${idBase}-error`
  const describedBy = error ? errorId : undefined

  let body
  if (value?.kind === 'existing') {
    body = (
      <div className="bg-muted flex flex-wrap items-center justify-between gap-2 rounded-xl p-3">
        <p className="text-foreground text-sm font-medium" aria-describedby={describedBy}>
          {t('selected', { name: value.fullName })}
        </p>
        <button
          type="button"
          onClick={() => onChange(null)}
          className="text-primary text-sm font-medium hover:underline"
        >
          {t('change_selection')}
        </button>
      </div>
    )
  } else if (creating) {
    const fullName = value?.kind === 'new' ? value.fullName : ''
    const gender: Gender = value?.kind === 'new' ? value.gender : 'unknown'
    body = (
      <div className="bg-muted space-y-3 rounded-xl p-3">
        <div>
          <label htmlFor={`${idBase}-new-name`} className="text-foreground mb-1 block text-sm">
            {t('new_name')}
          </label>
          <input
            id={`${idBase}-new-name`}
            type="text"
            value={fullName}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            onChange={(e) => onChange({ kind: 'new', fullName: e.target.value, gender })}
            className={fieldClass}
          />
        </div>
        <fieldset>
          <legend className="text-foreground mb-1 text-sm">{t('new_gender')}</legend>
          <div className="flex flex-wrap gap-2">
            {(['male', 'female', 'unknown'] as const).map((g) => (
              <label
                key={g}
                className="border-input has-[:checked]:bg-primary has-[:checked]:text-primary-foreground has-[:checked]:border-primary text-foreground flex cursor-pointer items-center rounded-full border px-4 py-2 text-sm"
              >
                <input
                  type="radio"
                  name={`${idBase}-new-gender`}
                  value={g}
                  checked={gender === g}
                  onChange={() => onChange({ kind: 'new', fullName, gender: g })}
                  className="sr-only"
                />
                {t(`gender_${g}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <button
          type="button"
          onClick={() => {
            setCreating(false)
            onChange(null)
          }}
          className="text-primary text-sm font-medium hover:underline"
        >
          {t('pick_existing')}
        </button>
      </div>
    )
  } else {
    body = (
      <div className="space-y-2">
        <input
          id={`${idBase}-search`}
          type="search"
          value={text}
          placeholder={t('search_placeholder')}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(e) => setText(e.target.value)}
          className={fieldClass}
        />
        {query.length > 0 &&
          (search.isFetching && hits.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('searching')}</p>
          ) : hits.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('no_results')}</p>
          ) : (
            <ul className="space-y-1">
              {hits.map((hit) => (
                <li key={hit.id}>
                  <button
                    type="button"
                    onClick={() =>
                      onChange({ kind: 'existing', id: hit.id, fullName: hit.fullName })
                    }
                    className="bg-card hover:bg-muted focus:ring-ring w-full rounded-xl px-3 py-2 text-left text-sm transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
                  >
                    {hit.fullName}
                  </button>
                </li>
              ))}
            </ul>
          ))}
        {allowCreate && (
          <button
            type="button"
            onClick={() => {
              setCreating(true)
              onChange({ kind: 'new', fullName: text.trim(), gender: 'unknown' })
            }}
            className="text-primary text-sm font-medium hover:underline"
          >
            {t('create_new')}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {value?.kind === 'existing' || creating ? (
        <p className="text-foreground text-sm font-semibold">{label}</p>
      ) : (
        <label htmlFor={`${idBase}-search`} className="text-foreground block text-sm font-semibold">
          {label}
        </label>
      )}
      {body}
      {error && (
        <p id={errorId} role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
    </div>
  )
}
