import axios from 'axios'

import { API_BASE_URL, apiClient } from '@/api/client'

/** «Общая статистика» (backend: apps.performance) — отдельный сайт
 * /monthly-performance. Всё считается на сервере; отсутствие данных — `null`,
 * а не 0. Доступ — JWT сотрудника (общий с LMS) или ключ «только чтение»
 * в заголовке `X-Dashboard-Key` (телевизор в офисе). */

/** Показатели дня — по расписанию именно этого дня (занятия группы в этот
 * день) и составу групп на эту дату. */
export type PerformanceMetric =
  | 'scheduled_groups'
  | 'held_groups'
  | 'scheduled_students'
  | 'attended_students'
  | 'attendance_percent'
  | 'homework_percent'

/** Метрики карточек. */
export type CardMetric = 'attendance_percent' | 'homework_percent' | 'scheduled_groups' | 'scheduled_students'

/** live — сегодня (считается на лету), provisional — ещё уточняется,
 * final — зафиксирован, computed — снимка ещё нет, восстановлено из записей
 * LMS, missing — данных нет, future — день ещё не наступил. */
export type PerformanceDayStatus = 'live' | 'provisional' | 'final' | 'computed' | 'missing' | 'future'

export interface PerformanceDay {
  date: string
  day: number
  weekday: number
  is_today: boolean
  is_future: boolean
  /** Есть показатели (не будущий день и не «нет данных»). */
  has_data: boolean
  /** В этот день по расписанию не было занятий. */
  no_lessons: boolean
  scheduled_groups: number | null
  held_groups: number | null
  scheduled_students: number | null
  attended_students: number | null
  expected_students: number | null
  attendance_percent: number | null
  homework_percent: number | null
  homework_results: number | null
  homework_done: number | null
  lessons_count: number | null
  held_lessons_count: number | null
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
  /** Для «Групп по расписанию» — сколько из них провели занятие в тот день. */
  held_groups?: number | null
  /** Для «Студентов по расписанию» — сколько из них посетили занятия. */
  attended_students?: number | null
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
  is_future_month: boolean
  generated_at: string
  timezone: string
  days: PerformanceDay[]
  summary: Record<CardMetric, PerformanceCard>
  trends: Record<TrendKey, TrendSeries>
  available_years: number[]
  can_edit: boolean
  access: { mode: 'key' | 'user'; name: string }
}

export type TrendKey = 'attendance' | 'homework' | 'groups' | 'students'

export interface TrendSeries {
  points: TrendPoint[]
  average: number | null
}

export interface MonthParams {
  year: number
  month: number
}

export type CorrectionPayload = Partial<Record<PerformanceMetric, number | null>> & { comment?: string }

export const DASHBOARD_KEY_HEADER = 'X-Dashboard-Key'

/** Запросы по ключу — без JWT и без обновления/сброса сессии LMS: неверный
 * ключ телевизора никогда не разлогинит сотрудника в этом браузере. */
const keyClient = axios.create({ baseURL: API_BASE_URL })

export const monthlyPerformanceApi = {
  /** `GET /monthly-performance/` — дни месяца, карточки и графики одним запросом.
   * С ключом — только ключ (телевизор не зависит от срока входа сотрудника). */
  month: (params: MonthParams, dashboardKey?: string | null): Promise<MonthlyPerformance> =>
    (dashboardKey
      ? keyClient.get<MonthlyPerformance>('/monthly-performance/', { params, headers: { [DASHBOARD_KEY_HEADER]: dashboardKey } })
      : apiClient.get<MonthlyPerformance>('/monthly-performance/', { params })
    ).then((r) => r.data),
  /** `PATCH /monthly-performance/snapshots/<date>/` — ручная корректировка (только с правом). */
  correct: (date: string, payload: CorrectionPayload) =>
    apiClient.patch(`/monthly-performance/snapshots/${date}/`, payload).then((r) => r.data),
}
