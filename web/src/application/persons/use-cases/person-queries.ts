import type {
  CursorPage,
  DocumentSummary,
  Marriage,
  ParentChild,
  Person,
  PersonBatchGetInput,
  PersonBatchGetResponse,
  PersonSummary,
  TimelineEvent,
} from '@/lib/types'
import type {
  PersonQueryRepository,
  PersonsListQuery,
} from '@/application/persons/ports/person-query-repository'

export async function listPersons(
  repository: PersonQueryRepository,
  params: PersonsListQuery,
): Promise<CursorPage<PersonSummary>> {
  return repository.list(params)
}

export async function searchPersons(
  repository: PersonQueryRepository,
  query: string,
  limit = 20,
): Promise<PersonSummary[]> {
  return repository.search(query, limit)
}

export async function getPerson(
  repository: PersonQueryRepository,
  id: string,
): Promise<Person> {
  return repository.get(id)
}

export async function getPersonMarriages(
  repository: PersonQueryRepository,
  id: string,
): Promise<Marriage[]> {
  return repository.getMarriages(id)
}

export async function getPersonParentChild(
  repository: PersonQueryRepository,
  id: string,
): Promise<ParentChild[]> {
  return repository.getParentChild(id)
}

export async function getPersonTimeline(
  repository: PersonQueryRepository,
  id: string,
): Promise<TimelineEvent[]> {
  return repository.getTimeline(id)
}

export async function getPersonDocuments(
  repository: PersonQueryRepository,
  id: string,
): Promise<DocumentSummary[]> {
  return repository.getDocuments(id)
}

export async function batchGetPersons(
  repository: PersonQueryRepository,
  input: PersonBatchGetInput,
): Promise<PersonBatchGetResponse> {
  return repository.batchGet(input)
}