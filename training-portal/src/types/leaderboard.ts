/** GET /api/v1/training/leaderboard/ */
export interface LeaderboardEntry {
  rank: number
  student_name: string
  /** percent 0–100 */
  score: number
  duration_seconds?: number
  finished_at: string
  test_id?: string
  test_title?: string
  /** sort=average|tests: one row per name over all results */
  average_score?: number
  best_score?: number
  completed_tests?: number
  passed_tests?: number
}

/** best — best result per name and test; average — average over all
 * results; tests — most completed tests. */
export type LeaderboardSort = 'best' | 'average' | 'tests'
