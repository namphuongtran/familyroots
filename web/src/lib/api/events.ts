import api from './axios'
import type { ClanEvent, UpcomingEvent, EventCreateInput, EventUpdateInput, ApiResponse, CursorPage } from '@/lib/types'

// ── Mock data ─────────────────────────────────────────────────────────────────
const MOCK_UPCOMING: UpcomingEvent[] = [
  {
    id: 'evt-1',
    clan_id: 'clan-1',
    person_id: '1',
    event_type: 'death_anniversary',
    title: 'Giỗ Tổ Nguyễn Văn Tổ',
    event_date: '2026-03-15',
    is_lunar_calendar: false,
    is_recurring: true,
    notify_days_before: 7,
    created_by: 'user-1',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    person_name: 'Nguyễn Văn Tổ',
    next_occurrence: '2026-03-15',
    days_until: 7,
  },
]

const isMock = !process.env.NEXT_PUBLIC_API_URL

export const eventsApi = {
  list: async (params?: { cursor?: string; limit?: number }): Promise<CursorPage<ClanEvent>> => {
    if (isMock) {
      return { data: MOCK_UPCOMING, next_cursor: null, has_more: false }
    }
    const { data } = await api.get<{ data: ClanEvent[] }>('/events', { params })
    return {
      data: data.data,
      next_cursor: null,
      has_more: false,
    }
  },

  getUpcoming: async (days = 30): Promise<UpcomingEvent[]> => {
    if (isMock) return MOCK_UPCOMING
    const { data } = await api.get<{ data: UpcomingEvent[] }>('/events/upcoming', {
      params: { days },
    })
    return data.data
  },

  get: async (id: string): Promise<ClanEvent> => {
    const { data } = await api.get<ApiResponse<ClanEvent>>(`/events/${id}`)
    return data.data
  },

  create: async (input: EventCreateInput): Promise<ClanEvent> => {
    const { data } = await api.post<ApiResponse<ClanEvent>>('/events', input)
    return data.data
  },

  update: async (id: string, input: EventUpdateInput): Promise<ClanEvent> => {
    const { data } = await api.patch<ApiResponse<ClanEvent>>(`/events/${id}`, input)
    return data.data
  },

  delete: (id: string) => api.delete(`/events/${id}`),
}
