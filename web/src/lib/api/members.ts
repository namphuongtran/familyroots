import api from './axios'
import type {
  Member,
  MemberSummary,
  MemberCreateInput,
  MemberUpdateInput,
  TimelineEvent,
  ApiResponse,
  CursorPage,
} from '@/lib/types'
import type { Relationship } from '@/lib/types/relationship'
import type { DocumentSummary } from '@/lib/types/document'

export interface MembersListParams {
  cursor?: string
  limit?: number
  generation?: number
  gender?: string
  is_alive?: boolean
  search?: string
}

// ── Mock data for offline/demo mode ──────────────────────────────────────────
const MOCK_MEMBERS: MemberSummary[] = [
  {
    id: '1',
    full_name: 'Nguyễn Văn Tổ',
    gender: 'male',
    birth_date: '1850-01-01',
    birth_date_approx: true,
    death_date: '1920-03-15',
    generation: 1,
    avatar_url: undefined,
    is_clan_member: true,
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
    is_clan_member: true,
  },
  {
    id: '3',
    full_name: 'Nguyễn Văn An',
    gender: 'male',
    birth_date: '1965-03-08',
    birth_date_approx: false,
    generation: 3,
    avatar_url: undefined,
    is_clan_member: true,
  },
]

const isMock = !process.env.NEXT_PUBLIC_API_URL

export const membersApi = {
  list: async (params: MembersListParams = {}): Promise<CursorPage<MemberSummary>> => {
    if (isMock) {
      return { data: MOCK_MEMBERS, next_cursor: null, has_more: false }
    }
    const { data } = await api.get<CursorPage<MemberSummary>>('/members', { params })
    return data
  },

  search: async (q: string, limit = 20): Promise<MemberSummary[]> => {
    if (isMock) {
      return MOCK_MEMBERS.filter((m) =>
        m.full_name.toLowerCase().includes(q.toLowerCase()),
      )
    }
    const { data } = await api.get<{ data: MemberSummary[] }>('/members/search', {
      params: { q, limit },
    })
    return data.data
  },

  get: async (id: string): Promise<Member> => {
    const { data } = await api.get<ApiResponse<Member>>(`/members/${id}`)
    return data.data
  },

  getRelationships: async (id: string): Promise<Relationship[]> => {
    const { data } = await api.get<ApiResponse<Relationship[]>>(
      `/members/${id}/relationships`,
    )
    return data.data
  },

  getTimeline: async (id: string): Promise<TimelineEvent[]> => {
    const { data } = await api.get<ApiResponse<TimelineEvent[]>>(
      `/members/${id}/timeline`,
    )
    return data.data
  },

  getDocuments: async (id: string): Promise<DocumentSummary[]> => {
    const { data } = await api.get<ApiResponse<DocumentSummary[]>>(
      `/members/${id}/documents`,
    )
    return data.data
  },

  create: async (input: MemberCreateInput): Promise<Member> => {
    const { data } = await api.post<ApiResponse<Member>>('/members', input)
    return data.data
  },

  update: async (id: string, input: MemberUpdateInput): Promise<Member> => {
    const { data } = await api.patch<ApiResponse<Member>>(`/members/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/members/${id}`),
}
