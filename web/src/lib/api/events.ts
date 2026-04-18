import api from './axios'
import type { ClanEvent, UpcomingEvent, EventCreateInput, EventUpdateInput, ApiResponse, CursorPage } from '@/lib/types'

export const eventsApi = {
  list: async (params?: { cursor?: string; limit?: number }): Promise<CursorPage<ClanEvent>> => {
    const { data } = await api.get<{ data: ClanEvent[] }>('/events', { params })
    return {
      data: data.data,
      next_cursor: null,
      has_more: false,
    }
  },

  getUpcoming: async (days = 30): Promise<UpcomingEvent[]> => {
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
