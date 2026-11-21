/**
 * Pure sorting helpers for the aside. Separate file so the sort rule can be
 * tested on its own, without mounting React — §3.3's
 * "Groups are ordered by `spouse_order` ascending, `null` last" is the one
 * invariant this aside pins, and it must survive a fixture whose rows arrive
 * in any order.
 */

import type { Marriage, ParentChild } from '@/domain/relationship/relationship'

/**
 * `spouse_order` ascending, `null` last. The stable fallback by `id` keeps
 * the sort deterministic when two edges share the same order (which the
 * backend's partial unique index rules out for same-orientation live rows,
 * but a legacy or divorced row can still collide).
 */
export function sortMarriagesBySpouseOrder(marriages: readonly Marriage[]): Marriage[] {
  return [...marriages].sort((a, b) => {
    if (a.spouseOrder === b.spouseOrder) return a.id.localeCompare(b.id)
    if (a.spouseOrder === null) return 1
    if (b.spouseOrder === null) return -1
    return a.spouseOrder - b.spouseOrder
  })
}

/**
 * Parent-child edges split by orientation relative to the target person,
 * then sorted by `birth_order` ascending, `null` last (same discipline as
 * marriages). A row whose neither end matches the target id is dropped
 * rather than placed in either group — a malformed server response is the
 * only way to reach that state, and rendering it in either group would be a
 * lie.
 */
export function splitParentChildByOrientation(
  rows: readonly ParentChild[],
  targetPersonId: string,
): { parents: ParentChild[]; children: ParentChild[] } {
  const parents: ParentChild[] = []
  const children: ParentChild[] = []
  for (const row of rows) {
    if (row.childId === targetPersonId) parents.push(row)
    else if (row.parentId === targetPersonId) children.push(row)
  }
  const byBirthOrder = (a: ParentChild, b: ParentChild) => {
    if (a.birthOrder === b.birthOrder) return a.id.localeCompare(b.id)
    if (a.birthOrder === null) return 1
    if (b.birthOrder === null) return -1
    return a.birthOrder - b.birthOrder
  }
  return { parents: parents.sort(byBirthOrder), children: children.sort(byBirthOrder) }
}
