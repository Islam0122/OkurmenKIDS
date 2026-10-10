import axios from 'axios'

import { API_BASE_URL } from '@/api/client'
import type { PublicOptions, PublicSchedule } from '@/types/publicSchedule'

/** A bare client: no auth header, no refresh-on-401 — the public schedule
 * never sends a visitor's (or a staff member's) token anywhere. */
const publicClient = axios.create({ baseURL: API_BASE_URL })

export interface PublicScheduleParams {
  start: string
  end: string
  group?: string
  trainer?: string
  room?: string
}

export const publicScheduleApi = {
  options: () => publicClient.get<PublicOptions>('/public/schedule/options/').then((r) => r.data),
  lessons: (params: PublicScheduleParams) => publicClient.get<PublicSchedule>('/public/schedule/', { params }).then((r) => r.data),
}
