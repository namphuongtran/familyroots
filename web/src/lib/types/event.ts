// Event types — aligned with backend EventResponse / UpcomingEvent

export type EventType =
  | 'death_anniversary'     // ngày giỗ
  | 'birthday'              // sinh nhật
  | 'wedding_anniversary'   // kỷ niệm ngày cưới
  | 'clan_ceremony'         // lễ kỵ / giỗ tổ
  | 'custom'

export interface ClanEvent {
  id: string
  clan_id: string
  person_id?: string
  event_type: EventType
  title: string
  description?: string
  event_date: string          // ISO date YYYY-MM-DD
  end_date?: string           // optional end date
  location?: string           // optional venue
  is_lunar_calendar: boolean  // âm lịch
  is_recurring: boolean
  notify_days_before: number  // 0–30
  created_by: string
  created_at: string
  updated_at: string
}

/** Upcoming event response from GET /events/upcoming */
export interface UpcomingEvent extends ClanEvent {
  person_name?: string
  person_avatar_url?: string
  next_occurrence: string     // ISO date of next occurrence
  days_until: number          // how many days until next occurrence
}

export interface EventCreateInput {
  person_id?: string
  event_type: EventType
  title: string
  description?: string
  event_date: string
  is_lunar_calendar: boolean
  is_recurring: boolean
  notify_days_before: number
}

export type EventUpdateInput = Partial<EventCreateInput>
