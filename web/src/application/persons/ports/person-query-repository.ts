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

export interface PersonsListQuery {
  cursor?: string
  limit?: number
  generation?: number
  gender?: string
  is_alive?: boolean
  search?: string
  profile?: 'summary' | 'detail' | 'full'
  include?: string
  fields?: string
}

export interface PersonQueryRepository {
  list(params: PersonsListQuery): Promise<CursorPage<PersonSummary>>
  search(query: string, limit: number): Promise<PersonSummary[]>
  get(id: string): Promise<Person>
  getMarriages(id: string): Promise<Marriage[]>
  getParentChild(id: string): Promise<ParentChild[]>
  getTimeline(id: string): Promise<TimelineEvent[]>
  getDocuments(id: string): Promise<DocumentSummary[]>
  batchGet(input: PersonBatchGetInput): Promise<PersonBatchGetResponse>
}