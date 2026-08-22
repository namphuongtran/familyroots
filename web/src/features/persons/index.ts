/**
 * Public surface of the `persons` slice. `cross-feature-only-via-index`
 * (`.dependency-cruiser.cjs`) requires every other feature — and, once
 * `src/app/**` composes a screen, the app tree too — to import this slice
 * through this file, never by reaching into `model/` or `api/` directly.
 *
 * This seed (S-029) only builds `model/` and `api/`, so that is all this file
 * re-exports today. `server/` and `hooks/` land with S-030, `ui/` later
 * still; each should be added here as it lands, not reached around.
 */

export type { Gender, Person, PersonActionResult, PersonSearchHit } from '@/domain/person/person'

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
  toPersonSearchHit,
} from './model/person-dto'

export type { HistoricalDateDto } from './model/historical-date-dto'
export { historicalDateDtoSchema, toHistoricalDate } from './model/historical-date-dto'

export type {
  GetPersonQuery,
  ListPersonsQuery,
  PersonsApiCallOptions,
  SearchPersonsQuery,
} from './api/persons-api'
export {
  batchGetPersons,
  createPerson,
  deletePerson,
  getPerson,
  listPersons,
  restorePerson,
  searchPersons,
  updatePerson,
} from './api/persons-api'
