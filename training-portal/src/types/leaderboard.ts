/** GET /api/v1/training/leaderboard/ */
export interface LeaderboardEntry {
  rank: number
  student_name: string
  /** percent 0–100 */
  score: number
  duration_seconds: number
  finished_at: string
  test_id: string
  test_title: string
}
