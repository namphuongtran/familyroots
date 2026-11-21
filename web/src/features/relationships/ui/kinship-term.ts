/**
 * Derives the kinship term shown in a RelationshipRow (spec §3.3 and §4.5).
 *
 * The contract today does not carry a server-localised `kinship_term` for
 * `MarriageResponse` or `ParentChildResponse` — the fields it does carry
 * (`spouse_order`, `relationship_type`, `status`) are what decides the term,
 * so these helpers compose the message key from those fields. When the
 * backend starts returning a term string, this file collapses to a pass-
 * through; it is the one place the derivation lives today.
 */

import type { Marriage } from '@/domain/relationship/relationship'

/**
 * §3.3's numbered wife labels. 1 → `spouse_order_1` (Vợ cả), 2 → `_2` (Vợ hai),
 * 3 → `_3` (Vợ ba), n → `_n` with `{order}`. `null` → `spouse_no_order`
 * (just "Vợ/Chồng"), per §3.3's "absence of it is not first" rule.
 */
export interface SpouseLabel {
  /** The namespaced message key for `t('relationship.<key>')`. */
  readonly key: string
  /** `{order: N}` when the key names a template variable; `null` otherwise. */
  readonly values: { order: number } | null
}

export function spouseLabelOf(marriage: Marriage): SpouseLabel {
  const order = marriage.spouseOrder
  if (order === null) return { key: 'spouse_no_order', values: null }
  if (order === 1) return { key: 'spouse_order_1', values: null }
  if (order === 2) return { key: 'spouse_order_2', values: null }
  if (order === 3) return { key: 'spouse_order_3', values: null }
  return { key: 'spouse_order_n', values: { order } }
}
