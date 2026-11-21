/**
 * đa thê: a father's children grouped under each wife (design spec § 3.3).
 *
 * - A child with a `motherId` goes in that wife's group. The group's order is the marriage's
 *   `spouse_order`; when it is unknown the group has no order. Absence is not "first".
 * - A child with no `motherId` goes in one final group, `unknown-mother` (`Chưa rõ mẹ`). It is
 *   never folded into the first wife.
 * - Groups sort by order ascending, `null` last, then the unknown-mother group.
 * - Within a group the backend's child order (birth order, birth date, name) is kept.
 *
 * Pure: no labels here. The UI turns `order` into `Vợ cả`/`Vợ hai`/… through next-intl.
 */

export interface GroupableChild {
  motherId: string | null
  motherSpouseOrder: number | null
}

export interface GroupableSpouse {
  id: string
  fullName: string
  spouseOrder: number | null
}

export type ChildGroup<C> =
  | {
      kind: 'wife'
      motherId: string
      /** The wife's name, from the father's spouses. `null` if she is not among them. */
      motherName: string | null
      order: number | null
      children: C[]
    }
  | { kind: 'unknown-mother'; children: C[] }

export function groupChildrenByMother<C extends GroupableChild>(
  children: readonly C[],
  spouses: readonly GroupableSpouse[],
): ChildGroup<C>[] {
  const wives = new Map<string, Extract<ChildGroup<C>, { kind: 'wife' }>>()
  const unknown: C[] = []

  for (const child of children) {
    if (child.motherId === null) {
      unknown.push(child)
      continue
    }
    let group = wives.get(child.motherId)
    if (!group) {
      const spouse = spouses.find((s) => s.id === child.motherId)
      group = {
        kind: 'wife',
        motherId: child.motherId,
        motherName: spouse?.fullName ?? null,
        order: child.motherSpouseOrder ?? spouse?.spouseOrder ?? null,
        children: [],
      }
      wives.set(child.motherId, group)
    }
    group.children.push(child)
  }

  // `Array.prototype.sort` is stable, so wives with equal (or both null) order keep the order
  // their first child appeared in.
  const groups: ChildGroup<C>[] = [...wives.values()].sort((a, b) => {
    if (a.order === b.order) return 0
    if (a.order === null) return 1
    if (b.order === null) return -1
    return a.order - b.order
  })
  if (unknown.length > 0) groups.push({ kind: 'unknown-mother', children: unknown })
  return groups
}

/** The children in group order, flattened: what a layout that cannot draw headers places. */
export function orderChildrenByMother<C extends GroupableChild>(
  children: readonly C[],
  spouses: readonly GroupableSpouse[],
): C[] {
  return groupChildrenByMother(children, spouses).flatMap((group) => group.children)
}
