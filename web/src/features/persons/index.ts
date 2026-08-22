/**
 * Public surface of the `persons` slice. `cross-feature-only-via-index`
 * (`.dependency-cruiser.cjs`) requires every other feature — and, once
 * `src/app/**` composes a screen, the app tree too — to import this slice
 * through this file, never by reaching into `model/`, `api/`, `server/`, or
 * `hooks/` directly.
 *
 * S-029 built `model/` and `api/`; S-030 adds `server/` (the repository and
 * query keys) and `hooks/` (TanStack Query). `ui/` lands later still, and
 * should be added here as it lands, not reached around.
 *
 * **The `../api/persons-api` functions are deliberately not re-exported here
 * any more.** Through S-029 this file re-exported them directly, because
 * `server/` did not exist yet and something had to be the entry point. Now
 * that the repository does the parsing, a caller reaching for the raw
 * `Promise<unknown>` transport instead of the parsed repository function
 * would be reaching *around* the one thing this seed built — so the public
 * surface below only ever hands out a parsed domain value, from the
 * repository or a hook. `api/persons-api.ts` still exists and is still
 * `Promise<unknown>` transport, same as S-029 left it; it is just no longer
 * part of what a caller outside this feature can see.
 */

export type {
  Gender,
  Person,
  PersonActionResult,
  PersonBatchResult,
  PersonSearchHit,
  PersonWriteResult,
} from '@/domain/person/person'

export type {
  BatchErrorDto,
  MessageDataDto,
  PersonResponseDto,
  PersonSearchResultDto,
} from './model/person-dto'
export {
  batchErrorDtoSchema,
  messageDataDtoSchema,
  personResponseDtoSchema,
  personSearchResultDtoSchema,
  toPerson,
  toPersonActionResult,
  toPersonBatchError,
  toPersonSearchHit,
} from './model/person-dto'

export type { HistoricalDateDto } from './model/historical-date-dto'
export { historicalDateDtoSchema, toHistoricalDate } from './model/historical-date-dto'

export type {
  GetPersonQuery,
  ListPersonsQuery,
  PersonsApiCallOptions,
  SearchPersonsQuery,
} from './server/persons-repository'
export {
  batchGetPersons,
  createPerson,
  deletePerson,
  getPerson,
  listPersons,
  restorePerson,
  searchPersons,
  updatePerson,
} from './server/persons-repository'
export { personsKeys } from './server/query-keys'

export type { PersonMutationOptions } from './hooks/use-person-mutations'
export {
  useCreatePerson,
  useDeletePerson,
  useRestorePerson,
  useUpdatePerson,
} from './hooks/use-person-mutations'

export type { PersonsQueryOptions } from './hooks/use-persons-queries'
export { usePerson, usePersonSearch, usePersonsList } from './hooks/use-persons-queries'

// `ui/` lands with S-031 — the persons list and detail screens. Exported
// here per this file's own header comment ("should be added here as it
// lands, not reached around").
export { PersonAvatar } from './ui/PersonAvatar'
export { PersonRow } from './ui/PersonRow'
export { PersonsErrorState } from './ui/PersonsErrorState'
export { PersonsList } from './ui/PersonsList'
export { PersonsListSkeleton } from './ui/PersonsListSkeleton'
export { PersonProfile } from './ui/PersonProfile'
export { formatHistoricalDate, isKnownDate } from './ui/format-person-date'
export { usePersonsRequestContext } from './ui/use-persons-request-context'
export type { PersonsRequestContext } from './ui/use-persons-request-context'

// Landed by S-032 — the create/edit form and its §7.7c conflict dialog.
// `HistoricalDateField`, `StaleWriteDialog`, `ForbiddenWriteDialog`, and the
// pure helpers in `person-form-schema.ts`/`stale-write-diff.ts` are
// deliberately not exported here: nothing outside this feature composes a
// form from smaller pieces today, and `PersonForm` is the one thing
// `app/[locale]/(dashboard)/members/{new,[id]/edit}/page.tsx` need.
export { PersonForm } from './ui/PersonForm'
export type { PersonFormProps } from './ui/PersonForm'
