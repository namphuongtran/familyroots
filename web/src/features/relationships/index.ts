/**
 * Public surface of the `relationships` slice. `cross-feature-only-via-index`
 * (`.dependency-cruiser.cjs`) requires every other feature — and the `app/`
 * tree — to import this slice through this file, never by reaching into
 * `model/`, `api/`, `server/`, `hooks/`, or `ui/` directly.
 *
 * The transport layer is deliberately not re-exported, same as persons: a
 * caller reaching for the raw `Promise<unknown>` `api/` hands back would be
 * reaching *around* the parsing the repository does. The public surface only
 * hands out parsed domain values (from the repository or a hook) and the UI
 * the issue's End state ships.
 */

export type {
  Marriage,
  MarriageStatus,
  MarriageWriteResult,
  ParentChild,
  ParentChildType,
  ParentChildWriteResult,
  RelationshipActionResult,
} from '@/domain/relationship/relationship'

export type { MarriageResponseDto } from './model/marriage-dto'
export { marriageResponseDtoSchema, toMarriage } from './model/marriage-dto'

export type { ParentChildResponseDto } from './model/parent-child-dto'
export { parentChildResponseDtoSchema, toParentChild } from './model/parent-child-dto'

export type { MessageDataDto } from './model/message-data-dto'
export { messageDataDtoSchema, toRelationshipActionResult } from './model/message-data-dto'

export type { HistoricalDateDto } from './model/historical-date-dto'
export { historicalDateDtoSchema, toHistoricalDate } from './model/historical-date-dto'

export type { RelationshipsApiCallOptions } from './server/relationships-repository'
export {
  createMarriage,
  createParentChild,
  deleteMarriage,
  deleteParentChild,
  getMarriage,
  getParentChild,
  listPersonMarriages,
  listPersonParentChild,
  updateMarriage,
  updateParentChild,
} from './server/relationships-repository'
export { relationshipsKeys } from './server/query-keys'

export type { RelationshipsQueryOptions } from './hooks/use-relationship-queries'
export { usePersonMarriages, usePersonParentChild } from './hooks/use-relationship-queries'

export { RelationshipsAside } from './ui/RelationshipsAside'
export { RelationshipEditorSheet } from './ui/RelationshipEditorSheet'
export type { RelationshipEditorSection } from './ui/RelationshipEditorSheet'
export type { RelationshipMutationOptions } from './hooks/use-relationship-mutations'
export {
  useCreateMarriage,
  useCreateParentChild,
  useUpdateMarriage,
} from './hooks/use-relationship-mutations'
export { RelationshipRow } from './ui/RelationshipRow'
export { spouseLabelOf } from './ui/kinship-term'
export { sortMarriagesBySpouseOrder, splitParentChildByOrientation } from './ui/relationship-sort'
