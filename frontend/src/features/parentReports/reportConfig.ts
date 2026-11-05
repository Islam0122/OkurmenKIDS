import { endOfWeek, format, startOfMonth, startOfWeek, subDays, subMonths, subWeeks } from 'date-fns'

import type {
  ComparisonTrend,
  ParentReportConfig,
  ParentReportFormat,
  ParentReportLanguage,
  ParentReportType,
  ReportPeriodKey,
  StudentReportStatus,
} from '@/types/parentReports'
import type { BadgeTone } from '@/components/ui/Badge'

export interface ReportPeriodOption {
  key: ReportPeriodKey
  label: string
  /** The dates the backend resolves this key to (shown to the trainer). Empty for `custom`. */
  dateFrom: string
  dateTo: string
}

const iso = (date: Date) => format(date, 'yyyy-MM-dd')

/** Mirrors apps.reports.services.periods (= the group KPI periods) — the
 * backend resolves the key itself; the dates here are for display only. */
export function getReportPeriods(now = new Date()): ReportPeriodOption[] {
  const monthStart = startOfMonth(now)
  const lastMonthStart = startOfMonth(subMonths(now, 1))
  return [
    { key: 'today', label: 'Сегодня', dateFrom: iso(now), dateTo: iso(now) },
    { key: 'last_7_days', label: 'Последние 7 дней', dateFrom: iso(subDays(now, 6)), dateTo: iso(now) },
    {
      key: 'this_week',
      label: 'Эта неделя',
      dateFrom: iso(startOfWeek(now, { weekStartsOn: 1 })),
      dateTo: iso(endOfWeek(now, { weekStartsOn: 1 })),
    },
    {
      key: 'last_week',
      label: 'Прошлая неделя',
      dateFrom: iso(startOfWeek(subWeeks(now, 1), { weekStartsOn: 1 })),
      dateTo: iso(endOfWeek(subWeeks(now, 1), { weekStartsOn: 1 })),
    },
    { key: 'this_month', label: 'Этот месяц', dateFrom: iso(monthStart), dateTo: iso(now) },
    { key: 'last_month', label: 'Прошлый месяц', dateFrom: iso(lastMonthStart), dateTo: iso(subDays(monthStart, 1)) },
    { key: 'custom', label: 'Произвольный период', dateFrom: '', dateTo: '' },
  ]
}

export const REPORT_TYPE_OPTIONS: { value: ParentReportType; label: string; hint: string }[] = [
  { value: 'group', label: 'Отчёт по группе', hint: 'Одна картинка для общего чата родителей' },
  { value: 'students', label: 'Индивидуальные отчёты', hint: 'Отдельный отчёт для родителей каждого студента' },
]

export const LANGUAGE_OPTIONS: { value: ParentReportLanguage; label: string }[] = [
  { value: 'ru', label: 'Русский' },
  { value: 'ky', label: 'Кыргызча' },
]

export const FORMAT_OPTIONS: { value: ParentReportFormat; label: string }[] = [
  { value: 'png', label: 'PNG-изображение' },
  { value: 'text', label: 'Текст для WhatsApp' },
  { value: 'both', label: 'Изображение и текст' },
]

export const OPTION_LABELS: { key: 'include_table' | 'include_group_stats' | 'include_recommendations' | 'include_comparison'; label: string }[] = [
  { key: 'include_table', label: 'Таблица студентов' },
  { key: 'include_group_stats', label: 'Статистика группы' },
  { key: 'include_recommendations', label: 'Рекомендации' },
  { key: 'include_comparison', label: 'Сравнение с прошлым периодом' },
]

export function defaultConfig(): ParentReportConfig {
  return {
    period: 'this_month',
    report_type: 'group',
    language: 'ru',
    output_format: 'both',
    include_table: true,
    include_group_stats: true,
    include_recommendations: true,
    include_comparison: true,
  }
}

export const STUDENT_STATUS_LABEL: Record<StudentReportStatus, string> = {
  excellent: 'Отлично',
  good: 'Хорошо',
  attention: 'Нужно внимание',
  support: 'Требуется поддержка',
  no_data: 'Нет данных',
}

export const STUDENT_STATUS_TONE: Record<StudentReportStatus, BadgeTone> = {
  excellent: 'success',
  good: 'success',
  attention: 'warning',
  support: 'danger',
  no_data: 'muted',
}

export const NO_DATA = 'Нет данных'

export function fmtPercent(value: number | null): string {
  if (value === null) return NO_DATA
  return `${String(Math.round(value * 10) / 10).replace('.', ',')}%`
}

export function fmtScore(value: number | null): string {
  if (value === null) return NO_DATA
  return `${String(Math.round(value * 10) / 10).replace('.', ',')}/10`
}

export function fmtChange(change: number | null, unit = ' п.п.'): string | null {
  if (change === null) return null
  const abs = String(Math.round(Math.abs(change) * 10) / 10).replace('.', ',')
  return `${change > 0 ? '+' : change < 0 ? '−' : '±'}${abs}${unit}`
}

export const TREND_CLASS: Record<ComparisonTrend, string> = {
  up: 'text-brand-600',
  down: 'text-danger',
  stable: 'text-ink-muted',
  no_data: 'text-ink-muted',
}
