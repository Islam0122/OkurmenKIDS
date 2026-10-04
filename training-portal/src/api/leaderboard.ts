import type { LeaderboardEntry, LeaderboardSort } from '@/types'

import { apiClient } from './client'

export const getLeaderboard = (testId?: string, limit?: number, sort?: LeaderboardSort) =>
  apiClient.get<LeaderboardEntry[]>('/leaderboard/', { query: { test: testId, limit, sort: sort && sort !== 'best' ? sort : undefined } })
