'use client'

import Link from 'next/link'
import { useLocale, useTranslations } from 'next-intl'
import type { Person } from '@/domain/person/person'
import { PersonAvatar } from '@/features/persons'

interface RelationshipRowProps {
  /**
   * Kinship term for this edge (spec §4.5), already localised. The caller
   * derives it from the server's `spouse_order` / `relationship_type` /
   * orientation via `kinship-term.ts` or by naming an `aside_parents` /
   * `aside_children` group. Not a message key on purpose: the label depends
   * on which end of the edge the viewer is on, which only the caller knows.
   */
  readonly kinshipTerm: string
  /**
   * The person on the other end of the edge. `null` when the batch lookup
   * for them has not resolved, or when they were omitted from it — the row
   * still renders with an "unknown person" placeholder rather than
   * disappearing, so the aside's count never silently shrinks.
   */
  readonly person: Person | null
  /**
   * Type chip text (spec §4.5), already localised. For a marriage this is the
   * `status` label; for a parent-child row it is the `relationship_type` label
   * (`Con đẻ` / `Con nuôi` / `Con riêng`).
   */
  readonly typeChip: string | null
  /**
   * Fallback id when no `person` could be looked up, so a reader can still
   * click through to the detail page without a name. Only used when
   * `person === null`.
   */
  readonly personId: string
}

/**
 * Spec §4.5's RelationshipRow: kinship term + person + type chip. One row
 * per edge, laid out the same way `PersonRow` lays out a list row — same
 * grid, same focus ring so T-07 keyboard focus is identical to the list.
 */
export function RelationshipRow({ kinshipTerm, person, typeChip, personId }: RelationshipRowProps) {
  const locale = useLocale()
  const t = useTranslations('relationship')
  const displayName = person?.fullName ?? t('unknown_person')

  return (
    <Link
      href={`/${locale}/members/${personId}`}
      className="bg-card hover:bg-muted focus:ring-ring flex items-center gap-3 rounded-2xl p-3 transition-colors focus:ring-2 focus:ring-offset-2 focus:outline-none"
      data-testid="relationship-row"
    >
      <PersonAvatar fullName={displayName} avatarUrl={person?.avatarUrl ?? null} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="text-muted-foreground text-xs">{kinshipTerm}</p>
        <p className="text-foreground truncate text-sm font-semibold">{displayName}</p>
      </div>
      {typeChip && (
        <span className="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-[11px]">
          {typeChip}
        </span>
      )}
    </Link>
  )
}
