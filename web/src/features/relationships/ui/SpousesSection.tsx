'use client'

import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { ChevronDown, ChevronUp } from 'lucide-react'
import type { Person } from '@/domain/person/person'
import type { Marriage } from '@/domain/relationship/relationship'
import type { components } from '@/generated/api-types'
import { renderHistoricalDate, type DatePrecision } from '@/domain/date/historical-date'
import type { RequestContext } from '@/shared/http/request-context'
import { StaleWriteDialog, type FieldChoice, type StaleWriteRow } from '@/features/persons'
import { useUpdateMarriage } from '../hooks/use-relationship-mutations'
import { getMarriage } from '../server/relationships-repository'
import { relationshipsKeys } from '../server/query-keys'
import { spouseLabelOf } from './kinship-term'
import { EndMarriageForm, type EndMarriageFields } from './EndMarriageForm'
import { quietButtonClass } from './editor-classes'
import { writeErrorText } from './write-error-text'
import {
  isStaleWrite,
  planSpouseReorder,
  rankedMarriages,
  type ReorderStep,
} from './relationship-editor-model'

type MarriageUpdateRequest = components['schemas']['MarriageUpdateRequest']
/** A marriage PATCH body without its version: what the user asked for. */
type MarriageFields = Omit<MarriageUpdateRequest, 'expected_version'>

/** The §7.7c conflict over one marriage PATCH, plus the reorder steps still to run after it. */
interface Conflict {
  marriageId: string
  spouseName: string
  mine: MarriageFields
  latest: Marriage
  rows: StaleWriteRow[]
  choices: Record<string, FieldChoice>
  repeated: boolean
  remaining: ReorderStep[]
  versions: Map<string, number>
}

interface SpousesSectionProps {
  readonly personId: string
  readonly marriages: readonly Marriage[]
  readonly people: ReadonlyMap<string, Person>
  readonly context: RequestContext
  readonly refreshAuth?: () => Promise<RequestContext | null>
  readonly onSaved: (warning: string | null) => void
}

function otherEnd(m: Marriage, personId: string): string {
  return m.person1Id === personId ? m.person2Id : m.person1Id
}

/**
 * The spouse list in rank order (spec §3.3) with up/down controls, and an "end marriage" form
 * per live marriage. Every write is a `PATCH /relationships/marriages/{id}` carrying the ADR-017
 * version the list was read at, or the version an earlier write of the same reorder returned.
 *
 * **A `409 stale_write` opens the persons form's dialog** (`StaleWriteDialog`), with one row per
 * field this write changes that the latest record holds differently. Saving the resolution
 * resends with the latest version and then runs whatever reorder steps were still to come.
 * Discarding stops there and rereads the list. A discarded reorder can leave the parked wife
 * with no rank, which the list then shows, for the editor to set again.
 */
export function SpousesSection({
  personId,
  marriages,
  people,
  context,
  refreshAuth,
  onSaved,
}: SpousesSectionProps) {
  const t = useTranslations('relationship_editor')
  const tRel = useTranslations('relationship')
  const tForm = useTranslations('member_form')
  const update = useUpdateMarriage({ context, refreshAuth })
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ending, setEnding] = useState<string | null>(null)
  const [endError, setEndError] = useState<string | null>(null)
  const [conflict, setConflict] = useState<Conflict | null>(null)

  const ranked = rankedMarriages(marriages)
  const divorced = marriages.filter((m) => m.status === 'divorced')
  const nameOf = (m: Marriage) =>
    people.get(otherEnd(m, personId))?.fullName ?? tRel('unknown_person')

  function orderText(order: number | null | undefined): string {
    return order == null ? t('order_none') : String(order)
  }

  function rowsFor(mine: MarriageFields, latest: Marriage): StaleWriteRow[] {
    const rows: StaleWriteRow[] = []
    const push = (field: string, label: string, a: string, b: string) => {
      if (a !== b) rows.push({ field, label, mine: a, latest: b, defaultChoice: 'mine' })
    }
    if ('spouse_order' in mine) {
      push(
        'spouse_order',
        t('spouse_order_label'),
        orderText(mine.spouse_order),
        orderText(latest.spouseOrder),
      )
    }
    if (mine.status != null) {
      push('status', t('status_label'), tRel(mine.status), tRel(latest.status))
    }
    if ('divorce_date_precision' in mine) {
      const mineDate = renderHistoricalDate({
        date: mine.divorce_date ?? null,
        precision: (mine.divorce_date_precision ?? 'unknown') as DatePrecision,
        display: mine.divorce_date_display ?? null,
        lunar: null,
      })
      const latestDate = renderHistoricalDate(latest.divorceDate)
      const text = (r: typeof mineDate) =>
        r.kind === 'exact' ? r.iso : r.kind === 'text' ? r.text : ''
      push('divorce_date', t('end_date'), text(mineDate), text(latestDate))
    }
    return rows
  }

  /** Reads the latest record and opens the dialog, or, when nothing differs, carries on. */
  async function openConflict(
    marriageId: string,
    mine: MarriageFields,
    repeated: boolean,
    remaining: ReorderStep[],
    versions: Map<string, number>,
  ): Promise<void> {
    let latest: Marriage
    try {
      latest = await getMarriage(marriageId, { context, refreshAuth })
    } catch (e) {
      setError(writeErrorText(t, e))
      return
    }
    versions.set(latest.id, latest.version)
    const rows = rowsFor(mine, latest)
    if (rows.length === 0) {
      // Someone else already wrote exactly this. Nothing to choose, so keep going.
      await runSteps(remaining, versions)
      return
    }
    const choices: Record<string, FieldChoice> = {}
    for (const row of rows) choices[row.field] = row.defaultChoice
    const m = marriages.find((x) => x.id === marriageId)
    setConflict({
      marriageId,
      spouseName: m ? nameOf(m) : tRel('unknown_person'),
      mine,
      latest,
      rows,
      choices,
      repeated,
      remaining,
      versions,
    })
  }

  /** Sends each step in order; a 409 hands the rest to the conflict dialog. */
  async function runSteps(steps: readonly ReorderStep[], versions: Map<string, number>) {
    setBusy(true)
    setError(null)
    try {
      for (let i = 0; i < steps.length; i++) {
        const step = steps[i]
        const version =
          step.expectedVersion === 'chained'
            ? (versions.get(step.marriageId) ?? 1)
            : step.expectedVersion
        const mine: MarriageFields = { spouse_order: step.spouseOrder }
        try {
          const { marriage } = await update.mutateAsync({
            id: step.marriageId,
            body: { ...mine, expected_version: version },
          })
          versions.set(marriage.id, marriage.version)
        } catch (e) {
          if (isStaleWrite(e)) {
            await openConflict(step.marriageId, mine, false, steps.slice(i + 1), versions)
            return
          }
          setError(writeErrorText(t, e))
          return
        }
      }
      if (steps.length > 0) onSaved(null)
    } finally {
      setBusy(false)
    }
  }

  async function move(index: number, direction: 'up' | 'down') {
    const steps = planSpouseReorder(ranked, index, direction)
    const versions = new Map<string, number>()
    for (const m of marriages) versions.set(m.id, m.version)
    await runSteps(steps, versions)
  }

  async function endMarriage(m: Marriage, fields: EndMarriageFields) {
    setBusy(true)
    setEndError(null)
    try {
      await update.mutateAsync({ id: m.id, body: { ...fields, expected_version: m.version } })
      setEnding(null)
      onSaved(null)
    } catch (e) {
      if (isStaleWrite(e)) {
        setEnding(null)
        await openConflict(m.id, fields, false, [], new Map([[m.id, m.version]]))
        return
      }
      setEndError(writeErrorText(t, e))
    } finally {
      setBusy(false)
    }
  }

  async function saveResolved() {
    if (!conflict) return
    const body: MarriageFields = {}
    const mine = conflict.mine as Record<string, unknown>
    const out = body as Record<string, unknown>
    for (const key of Object.keys(mine)) {
      const rowField = key.startsWith('divorce_date') ? 'divorce_date' : key
      const choice = conflict.choices[rowField]
      // A field with no row already reads the same on the server: resending it is harmless.
      if (choice === undefined || choice === 'mine') out[key] = mine[key]
    }
    const { remaining, versions, latest } = conflict
    setBusy(true)
    try {
      const { marriage } = await update.mutateAsync({
        id: conflict.marriageId,
        body: { ...body, expected_version: latest.version },
      })
      versions.set(marriage.id, marriage.version)
      setConflict(null)
    } catch (e) {
      if (isStaleWrite(e)) {
        await openConflict(conflict.marriageId, conflict.mine, true, remaining, versions)
        return
      }
      setConflict(null)
      setError(writeErrorText(t, e))
      return
    } finally {
      setBusy(false)
    }
    if (remaining.length > 0) await runSteps(remaining, versions)
    else onSaved(null)
  }

  const copyText = conflict
    ? conflict.rows.map((row) => `${row.label}: ${row.mine}`).join('\n')
    : ''

  return (
    <div className="space-y-4">
      {ranked.length === 0 && divorced.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t('no_spouses')}</p>
      ) : (
        <ol className="space-y-2" aria-label={t('spouse_list')}>
          {ranked.map((m, index) => {
            const name = nameOf(m)
            const label = spouseLabelOf(m)
            return (
              <li
                key={m.id}
                className="bg-muted space-y-2 rounded-xl p-3"
                data-testid="spouse-item"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <div className="min-w-0 flex-1 basis-32">
                    <p className="text-muted-foreground text-xs">
                      {label.values ? tRel(label.key, label.values) : tRel(label.key)}
                      {' · '}
                      {tRel(m.status)}
                    </p>
                    <p className="text-foreground text-sm font-semibold break-words">{name}</p>
                  </div>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      aria-label={t('move_up', { name })}
                      disabled={busy || index === 0}
                      onClick={() => void move(index, 'up')}
                      className={quietButtonClass}
                    >
                      <ChevronUp className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label={t('move_down', { name })}
                      disabled={busy || index === ranked.length - 1}
                      onClick={() => void move(index, 'down')}
                      className={quietButtonClass}
                    >
                      <ChevronDown className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </div>
                {m.status === 'married' &&
                  (ending === m.id ? (
                    <EndMarriageForm
                      idBase={`end-${m.id}`}
                      saving={busy}
                      error={endError}
                      onSubmit={(fields) => void endMarriage(m, fields)}
                      onCancel={() => {
                        setEnding(null)
                        setEndError(null)
                      }}
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setEnding(m.id)
                        setEndError(null)
                      }}
                      className="text-primary text-sm font-medium hover:underline"
                    >
                      {t('end_marriage', { name })}
                    </button>
                  ))}
              </li>
            )
          })}
          {divorced.map((m) => (
            <li key={m.id} className="bg-muted rounded-xl p-3" data-testid="spouse-item">
              <p className="text-muted-foreground text-xs">{tRel(m.status)}</p>
              <p className="text-foreground text-sm font-semibold break-words">{nameOf(m)}</p>
            </li>
          ))}
        </ol>
      )}

      {busy && (
        <p role="status" className="text-muted-foreground text-sm">
          {tForm('saving')}
        </p>
      )}
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <StaleWriteDialog
        open={conflict !== null}
        personName={conflict?.spouseName ?? ''}
        rows={conflict?.rows ?? []}
        repeatedConflict={conflict?.repeated ?? false}
        choices={conflict?.choices ?? {}}
        onChoiceChange={(field, choice) =>
          setConflict((c) => (c ? { ...c, choices: { ...c.choices, [field]: choice } } : c))
        }
        onSaveResolved={() => void saveResolved()}
        onDiscardReload={() => {
          setConflict(null)
          void queryClient.invalidateQueries({ queryKey: relationshipsKeys.all(context.clanId) })
        }}
        onCopyMine={async () => {
          try {
            await navigator.clipboard.writeText(copyText)
            return true
          } catch {
            return false
          }
        }}
        copyText={copyText}
        saving={busy}
      />
    </div>
  )
}
