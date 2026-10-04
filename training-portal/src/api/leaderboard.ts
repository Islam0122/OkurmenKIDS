import type { LeaderboardEntry } from '@/types'

import { apiClient } from './client'

export const getLeaderboard = (testId?: string, limit?: number) =>
  apiClient.get<LeaderboardEntry[]>('/leaderboard/', { query: { test: testId, limit } })
