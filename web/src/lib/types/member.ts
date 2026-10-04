// `PersonSummary` is all that is left here, and the tree slice owns it (ADR-060 § 2's
// fallback). `src/lib/types/tree.ts`'s `RelationshipPath.from_person`/`to_person` types against
// it, and `features/persons` has no replacement for tree's wire shape. The tree slice deletes
// this file when it replaces that shape.
//
// The persons slice deleted the legacy `Person` with its last reader,
// `src/lib/hooks/useMembers.ts`. New code uses `Person` from `@/features/persons`.

/** Lightweight person summary used in lists and tree nodes */
export interface PersonSummary {
  id: string
  full_name: string
  posthumous_name?: string
  gender: 'male' | 'female' | 'unknown'
  birth_date?: string
  birth_date_approx: boolean
  death_date?: string
  generation?: number
  avatar_url?: string
  membership_role?: 'blood' | 'spouse' | 'adopted'
  is_founder?: boolean
}
