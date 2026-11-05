import { apiClient } from '@/api/client'

/** «Общая статистика» (backend: apps.performance). Всё считается на сервере;
 * отсутствие данных — `null`, а не 0. */

export type PerformanceMetric = 'attendance_percent' | 'homework_percent' | 'active_groups' | 'active_students'

/** live — сегодня (считается на лету), provisional — ещё уточняется,
 * final — зафиксирован, missing — снимка нет, future — день ещё не наступил. */
export type PerformanceDayStatus = 'live' | 'provisional' | 'final' | 'missing' | 'future'

export interface PerformanceDay {
  date: string
  day: number
  weekday: number
  is_today: boolean
  is_future: boolean
  attendance_percent: number | null
  attendance_marked: number
  attendance_attended: number
  homework_percent: number | null
  homework_results: number
  homework_done: number
  lessons_count: number
  active_groups: number | null
  active_students: number | null
  status: PerformanceDayStatus
  manual_fields: PerformanceMetric[]
  manual_comment: string
  computed_at: string | null
}

export interface PerformanceCard {
  value: number | null
  date: string | null
  previous_value: number | null
  previous_date: string | null
  change: number | null
  month_average?: number | null
}

export interface TrendPoint {
  date: string
  day: number
  value: number | null
}

export interface MonthlyPerformance {
  year: number
  month: number
  month_label: string
  today: string
  is_current_month: boolean
  generated_at: string
  timezone: string
  days: PerformanceDay[]
  summary: Record<PerformanceMetric, PerformanceCard>
  trends: {
    attendance: { points: TrendPoint[]; average: number | null }
    homework: { points: TrendPoint[]; average: number | null }
  }
  available_years: number[]
  can_edit: boolean
}

export interface MonthParams {
  year: number
  month: number
}

export type CorrectionPayload = Partial<Record<PerformanceMetric, number | null>> & { comment?: string }

export const monthlyPerformanceApi = {
  /** `GET /monthly-performance/` — дни месяца, карточки и графики одним запросом. */
  month: (params: MonthParams): Promise<MonthlyPerformance> =>
    apiClient.get<MonthlyPerformance>('/monthly-performance/', { params }).then((r) => r.data),
  /** `PATCH /monthly-performance/snapshots/<date>/` — ручная корректировка (только с правом). */
  correct: (date: string, payload: CorrectionPayload) =>
    apiClient.patch(`/monthly-performance/snapshots/${date}/`, payload).then((r) => r.data),
}
