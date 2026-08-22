/**
 * Presentation-only formatting for `HistoricalDate`, built on top of the
 * domain render rule (`@/domain/date/historical-date.ts`) rather than
 * re-implementing it. That module's own header comment says it decides
 * *what* to show, never *how* to format it, and keeps itself free of any
 * `Intl`/locale dependency on purpose — this file is the first screen-facing
 * consumer that turns an `exact` value into an actual locale-formatted
 * string.
 *
 * Deliberately not `src/domain/`: choosing a date style is a presentation
 * decision, and `domain-is-pure` forbids this layer from reaching for
 * anything that is not plain data anyway. Kept persons-local for now, same
 * "copy on first use, factor out on second" call S-029/S-030 made for
 * `historical-date-dto.ts` (`web/CLAUDE.md`, "The `persons` slice") — the
 * next date-bearing slice (marriages, events, tree nodes) that needs this
 * exact formatting should factor it out rather than ship a third copy.
 */

import { renderHistoricalDate, type HistoricalDate } from '@/domain/date/historical-date'
import type { Person } from '@/domain/person/person'

/**
 * Renders the contract's precedence rule (`date` when exact, else `display`,
 * else `date`, else "unknown") into a string a screen can print directly.
 * `locale` is a plain string rather than the narrower `LocaleCode` union —
 * this only ever feeds `Intl.DateTimeFormat`, which accepts any BCP 47 tag.
 */
export function formatHistoricalDate(
  value: HistoricalDate | null | undefined,
  locale: string,
  unknownLabel: string,
): string {
  const rendered = renderHistoricalDate(value)
  switch (rendered.kind) {
    case 'exact': {
      const parsed = new Date(rendered.iso)
      if (Number.isNaN(parsed.getTime())) return rendered.iso
      return new Intl.DateTimeFormat(locale, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        // The wire value is a calendar date with no time-of-day meaning
        // (`new Date('1948-08-15')` parses as UTC midnight). Formatting in
        // the host's local zone would print the previous day west of UTC —
        // pinning UTC is what keeps the printed date the one the record
        // actually names, regardless of where this renders.
        timeZone: 'UTC',
      }).format(parsed)
    }
    case 'text':
      return rendered.text
    case 'unknown':
      return unknownLabel
  }
}

/** Whether the domain render rule resolved to anything at all — see `PersonRow`'s lifespan line. */
export function isKnownDate(value: HistoricalDate | null | undefined): boolean {
  return renderHistoricalDate(value).kind !== 'unknown'
}

type SparseCheckFields = Pick<
  Person,
  | 'birthName'
  | 'courtesyName'
  | 'posthumousName'
  | 'aliasName'
  | 'titleRank'
  | 'birthPlace'
  | 'deathPlace'
  | 'residencePlace'
  | 'burialPlace'
  | 'tombLocation'
  | 'birthDate'
  | 'deathDate'
  | 'biography'
  | 'notes'
>

/**
 * Spec §7.6's "sparse record" state: "a person with nothing but a name is
 * valid and must look intentional." Pulled out of `PersonProfile.tsx` so the
 * rule driving that collapse is unit-testable without rendering a Server
 * Component, which nothing in this repo has a harness for yet (no
 * `next-intl/server` mock exists in any test today).
 */
export function personHasVisibleDetail(person: SparseCheckFields): boolean {
  const hasNameField = Boolean(
    person.birthName ||
    person.courtesyName ||
    person.posthumousName ||
    person.aliasName ||
    person.titleRank,
  )
  const hasPlaceField = Boolean(
    person.birthPlace ||
    person.deathPlace ||
    person.residencePlace ||
    person.burialPlace ||
    person.tombLocation,
  )
  const hasDate = isKnownDate(person.birthDate) || isKnownDate(person.deathDate)
  return (
    hasNameField || hasPlaceField || hasDate || Boolean(person.biography) || Boolean(person.notes)
  )
}
