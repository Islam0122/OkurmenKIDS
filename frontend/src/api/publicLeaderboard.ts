import axios from 'axios'

import { API_BASE_URL } from '@/api/client'
import type { GroupBoard, LeaderboardMeta, LeaderboardPeriodType, StudentBoard } from '@/types/leaderboard'

/** A bare client: no auth header, no refresh-on-401 — the public
 * leaderboard never sends a visitor's (or a staff member's) token anywhere. */
const publicClient = axios.create({ baseURL: API_BASE_URL })

export interface PeriodParams {
  period: LeaderboardPeriodType
  year?: number
  month?: number
  week_start?: string
}

export interface BoardParams extends PeriodParams {
  q?: string
  group?: string
  course?: string
  order?: 'desc' | 'asc'
  page?: number
  page_size?: number
}

/** Drops empty values so the URL (and the server cache key) stays canonical. */
function clean(params: object): Record<string, string | number> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
}

export const publicLeaderboardApi = {
  meta: () => publicClient.get<LeaderboardMeta>('/public/leaderboard/meta/').then((r) => r.data),
  students: (params: BoardParams) =>
    publicClient.get<StudentBoard>('/public/leaderboard/students/', { params: clean(params) }).then((r) => r.data),
  groups: (params: Omit<BoardParams, 'group'>) =>
    publicClient.get<GroupBoard>('/public/leaderboard/groups/', { params: clean(params) }).then((r) => r.data),
}
