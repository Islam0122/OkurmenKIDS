/** The public leaderboard API (/api/v1/public/leaderboard/*) — a closed
 * whitelist: public names, opaque keys, group/course names and XP. */

export type LeaderboardPeriodType = 'year' | 'month' | 'week'

export interface LeaderboardPeriod {
  type: LeaderboardPeriodType
  start: string
  end: string
  is_current: boolean
  year?: number
  month?: number
  week_start?: string
}

export interface LeaderboardRef {
  key: string
  name: string
}

/** Against the previous comparable period; null — nothing to compare with. */
export type RankChange = { status: 'up' | 'down' | 'same' | 'new'; value: number } | null

export interface XpBreakdown {
  attendance: number
  homework: number
  tests: number
}

export interface LeaderboardStudent {
  key: string
  rank: number
  name: string
  initials: string
  /** The student asked not to be listed by name. */
  hidden: boolean
  group: LeaderboardRef | null
  course: LeaderboardRef | null
  xp: number
  breakdown: XpBreakdown
  change: RankChange
}

export interface LeaderboardGroupMember {
  name: string
  initials: string
  xp: number
}

export interface LeaderboardGroup {
  key: string
  rank: number
  name: string
  course: LeaderboardRef | null
  members: number
  active_students: number
  total_xp: number
  average_xp: number
  top_members: LeaderboardGroupMember[]
  change: RankChange
}

export interface LeaderboardPage<T> {
  period: LeaderboardPeriod
  previous_period: LeaderboardPeriod
  generated_at: string
  /** Everyone ranked in the period (unfiltered). */
  participants: number
  /** Global top 3 (unfiltered). */
  podium: T[]
  /** Rows matching the filters. */
  count: number
  page: number
  page_size: number
  num_pages: number
  results: T[]
}

export type StudentBoard = LeaderboardPage<LeaderboardStudent>
export type GroupBoard = LeaderboardPage<LeaderboardGroup> & { students_ranked: number }

export interface LeaderboardRules {
  attendance_present: number
  attendance_late: number
  homework_done: number
  homework_late: number
  homework_grade_max: number
  test_max: number
  group_method: 'average'
  week_starts: 'monday'
  timezone: string
}

export interface LeaderboardMeta {
  today: string
  timezone: string
  current: { year: number; month: number; week_start: string }
  first_date: string | null
  years: number[]
  groups: { key: string; name: string; course: string | null }[]
  courses: LeaderboardRef[]
  rules: LeaderboardRules
  last_activity: string | null
}
