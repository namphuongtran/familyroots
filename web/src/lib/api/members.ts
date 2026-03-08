import api from './axios'
import type {
  Person,
  PersonSummary,
  PersonCreateInput,
  PersonUpdateInput,
  TimelineEvent,
  ApiResponse,
  CursorPage,
} from '@/lib/types'
import type { Marriage, ParentChild } from '@/lib/types/relationship'
import type { DocumentSummary } from '@/lib/types/document'

export interface PersonsListParams {
  cursor?: string
  limit?: number
  generation?: number
  gender?: string
  is_alive?: boolean
  search?: string
}

// ── Mock data for offline/demo mode ──────────────────────────────────────────
const MOCK_PERSONS: PersonSummary[] = [
  {
    id: '1',
    full_name: 'Nguyễn Văn Tổ',
    gender: 'male',
    birth_date: '1850-01-01',
    birth_date_approx: true,
    death_date: '1920-03-15',
    generation: 1,
    avatar_url: undefined,
    membership_role: 'blood',
    is_founder: true,
  },
  {
    id: '2',
    full_name: 'Nguyễn Thị Hoa',
    gender: 'female',
    birth_date: '1880-06-12',
    birth_date_approx: false,
    death_date: '1955-09-20',
    generation: 2,
    avatar_url: undefined,
    membership_role: 'blood',
  },
  {
    id: '3',
    full_name: 'Nguyễn Văn An',
    gender: 'male',
    birth_date: '1965-03-08',
    birth_date_approx: false,
    generation: 3,
    avatar_url: undefined,
    membership_role: 'blood',
  },
]

const isMock = !process.env.NEXT_PUBLIC_API_URL

export const personsApi = {
  list: async (params: PersonsListParams = {}): Promise<CursorPage<PersonSummary>> => {
    if (isMock) {
      return { data: MOCK_PERSONS, next_cursor: null, has_more: false }
    }
    const { data } = await api.get<CursorPage<PersonSummary>>('/persons', { params })
    return data
  },

  search: async (q: string, limit = 20): Promise<PersonSummary[]> => {
    if (isMock) {
      return MOCK_PERSONS.filter((m) =>
        m.full_name.toLowerCase().includes(q.toLowerCase()),
      )
    }
    const { data } = await api.get<{ data: PersonSummary[] }>('/persons/search', {
      params: { q, limit },
    })
    return data.data
  },

  get: async (id: string): Promise<Person> => {
    const { data } = await api.get<ApiResponse<Person>>(`/persons/${id}`)
    return data.data
  },

  getMarriages: async (id: string): Promise<Marriage[]> => {
    const { data } = await api.get<ApiResponse<Marriage[]>>(
      `/persons/${id}/marriages`,
    )
    return data.data
  },

  getParentChild: async (id: string): Promise<ParentChild[]> => {
    const { data } = await api.get<ApiResponse<ParentChild[]>>(
      `/persons/${id}/parent-child`,
    )
    return data.data
  },

  getTimeline: async (id: string): Promise<TimelineEvent[]> => {
    const { data } = await api.get<ApiResponse<TimelineEvent[]>>(
      `/persons/${id}/timeline`,
    )
    return data.data
  },

  getDocuments: async (id: string): Promise<DocumentSummary[]> => {
    const { data } = await api.get<ApiResponse<DocumentSummary[]>>(
      `/persons/${id}/documents`,
    )
    return data.data
  },

  create: async (input: PersonCreateInput): Promise<Person> => {
    const { data } = await api.post<ApiResponse<Person>>('/persons', input)
    return data.data
  },

  update: async (id: string, input: PersonUpdateInput): Promise<Person> => {
    const { data } = await api.patch<ApiResponse<Person>>(`/persons/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/persons/${id}`),
}
