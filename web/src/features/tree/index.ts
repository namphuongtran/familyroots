/**
 * Public surface of the `tree` slice. `cross-feature-only-via-index` requires every other feature,
 * and `src/app`, to import this slice through this file. The raw `api/` transport is not
 * re-exported, as in persons and relationships: callers get parsed domain values only.
 */

export type {
  FamilyTree,
  FocusAncestor,
  FocusView,
  TreePerson,
  TreeSpouse,
} from '@/domain/tree/tree'

export type { GetFocusQuery, GetTreeQuery, TreeApiCallOptions } from './server/tree-repository'
export { getFocus, getTree } from './server/tree-repository'
export { treeKeys } from './server/query-keys'

export type { TreeQueryOptions } from './hooks/use-tree-queries'
export { useFamilyTree, useTreeFocus } from './hooks/use-tree-queries'

export { TreeScreen } from './ui/TreeScreen'
