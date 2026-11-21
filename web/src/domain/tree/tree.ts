/**
 * The tree read model (docs/contracts/rest-tree-api.md, docs/contracts/tree-focus.md) in domain
 * shape: camelCase, and every "key absent" normalised to `null`. Types only.
 *
 * `generation` is đời from the backend's single authority (ADR-027) and is legitimately `null`
 * when a person is not descended from a founder. Nothing here turns that into a number.
 */

import type { HistoricalDate } from '@/domain/date/historical-date'

/** One spouse attached to a tree node (`SpouseNode`). */
export interface TreeSpouse {
  id: string
  fullName: string
  gender: string
  birthDate: HistoricalDate | null
  deathDate: HistoricalDate | null
  avatarUrl: string | null
  status: string
  /** The order of this marriage for the node it hangs off: 1 = vợ cả. `null` when not recorded. */
  spouseOrder: number | null
  membershipRole: string | null
}

/**
 * One person in a tree response. `GET /tree` and `GET /tree/focus/{id}` both map into this;
 * `hasMoreDescendants` and the branch fields are focus-only, so they are `false`/`null` on `/tree`.
 */
export interface TreePerson {
  id: string
  fullName: string
  gender: string
  birthDate: HistoricalDate | null
  deathDate: HistoricalDate | null
  avatarUrl: string | null
  membershipRole: string | null
  isFounder: boolean
  /** đời. `null` is a real value: "not yet connected to the founder" (spec § 3.2). */
  generation: number | null
  /** The child's female parent, which wife. `null` when no mother edge is recorded. */
  motherId: string | null
  /** That mother's `spouse_order` in her marriage to the father. `null` when unknown. */
  motherSpouseOrder: number | null
  /**
   * A pedigree-collapse stub (ADR-027): the same person renders in full elsewhere in the same
   * payload. `children`/`spouses` are always empty on a stub.
   */
  isPedigreeStub: boolean
  hasMoreDescendants: boolean
  spouses: TreeSpouse[]
  children: TreePerson[]
}

/** `GET /tree`. */
export interface FamilyTree {
  root: TreePerson
  totalPersons: number
  totalGenerations: number
}

/** One breadcrumb ancestor in a focus view, thủy-tổ-first. */
export interface FocusAncestor {
  id: string
  fullName: string
  gender: string
  avatarUrl: string | null
  generation: number | null
  isFounder: boolean
}

/** `GET /tree/focus/{person_id}`. */
export interface FocusView {
  focusPersonId: string
  generationOfFocus: number | null
  ancestors: FocusAncestor[]
  subtree: TreePerson | null
}
