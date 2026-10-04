import { apiClient } from './client'

export interface EventResponse {
  tab_switch_count: number
  violation_count: number
  max_tab_switches: number | null
}

/** An Exam Mode event (tab switch, fullscreen exit, copy attempt…) — logged by the backend. */
export const postEvent = (attemptId: string, token: string, eventType: string, question?: number, keepalive = false) =>
  apiClient.post<EventResponse>(
    `/attempts/${encodeURIComponent(attemptId)}/events/`,
    { event_type: eventType, metadata: question ? { question } : {} },
    { token, keepalive },
  )
