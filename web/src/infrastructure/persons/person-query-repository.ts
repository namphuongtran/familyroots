import type {
  PersonQueryRepository,
  PersonsListQuery,
} from '@/application/persons/ports/person-query-repository'
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
import { personsApi } from '@/lib/api/members'

export class HttpPersonQueryRepository implements PersonQueryRepository {
  async list(params: PersonsListQuery): Promise<CursorPage<PersonSummary>> {
    return personsApi.list(params)
  }

  async search(query: string, limit: number): Promise<PersonSummary[]> {
    return personsApi.search(query, limit)
  }

  async get(id: string): Promise<Person> {
    return personsApi.get(id)
  }

  async getMarriages(id: string): Promise<Marriage[]> {
    return personsApi.getMarriages(id)
  }

  async getParentChild(id: string): Promise<ParentChild[]> {
    return personsApi.getParentChild(id)
  }

  async getTimeline(id: string): Promise<TimelineEvent[]> {
    return personsApi.getTimeline(id)
  }

  async getDocuments(id: string): Promise<DocumentSummary[]> {
    return personsApi.getDocuments(id)
  }

  async batchGet(input: PersonBatchGetInput): Promise<PersonBatchGetResponse> {
    return personsApi.batchGet(input)
  }
}

export const personQueryRepository = new HttpPersonQueryRepository()