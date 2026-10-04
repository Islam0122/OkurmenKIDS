import type { ReportMetrics as Metrics } from '@/types/worklog'
import { formatDate } from '@/utils/format'

/** Russian labels of the figures apps.worklog.metrics computes. */
const LABELS: Record<string, string> = {
  groups: 'Группы',
  trainers: 'Тренеры',
  students: 'Студенты',
  homework: 'Домашние задания',
  kpi: 'KPI',
  tests: 'Тесты и экзамены',
  quality: 'Контроль качества',
  exams: 'Экзамены',
  lessons: 'Занятия',
  total: 'Всего',
  active: 'Активных',
  new: 'Новых',
  closed: 'Закрыто',
  left: 'Ушли',
  with_problems: 'С проблемами',
  problem_names: 'Требуют внимания',
  low_attendance: 'С низкой посещаемостью',
  low_results: 'С низкими результатами',
  average_completion: 'Средний процент выполнения',
  groups_below_norm: 'Групп ниже нормы',
  attendance: 'Посещаемость',
  results: 'Результаты',
  progress: 'Прогресс',
  academy_kpi: 'KPI академии',
  average_trainer_kpi: 'Средний KPI тренеров',
  tests_held: 'Проведено тестов',
  exams_held: 'Проведено экзаменов',
  average_score: 'Средний результат',
  students_below_passing: 'Студентов ниже минимума',
  groups_with_exam: 'Групп сдали экзамен',
  groups_passed: 'Групп сдали',
  groups_total: 'Групп всего',
  students_below: 'Студентов ниже нормы',
  lessons_visited: 'Посещено занятий',
  trainers_checked: 'Проверено тренеров',
  problems_found: 'Выявлено проблем',
  problems_resolved: 'Исправлено',
  problems_in_progress: 'В работе',
  meetings: 'Собраний',
  held: 'Проведено',
  cancelled: 'Отменено',
  due: 'По плану',
  lessons_held: 'Проведено занятий',
  kpi_status: 'Оценка KPI',
  lesson_visits: 'Проверок занятий',
  lesson_visit_average: 'Средняя оценка проверок',
  date: 'Дата',
  time: 'Время',
  group: 'Группа',
  teacher: 'Тренер',
  subject: 'Предмет',
  room: 'Кабинет',
  status: 'Статус',
  lesson: 'Занятие',
  student: 'Студент',
  entries: 'Записей журнала за день',
}

/** Keys whose number is a percentage. */
const PERCENT = new Set([
  'attendance',
  'homework',
  'results',
  'progress',
  'academy_kpi',
  'average_trainer_kpi',
  'average_completion',
  'kpi',
  'lessons_held',
])

const SKIP = new Set(['period', 'id'])

function isRef(value: unknown): value is { name: string } {
  return typeof value === 'object' && value !== null && 'name' in value && !Array.isArray(value)
}

function format(key: string, value: unknown, parent?: string): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') {
    if (PERCENT.has(key) && parent !== 'tests' && parent !== 'lessons') return `${value}%`
    // Attempt scores are 0–100.
    if (key === 'average_score' && (parent === 'tests' || parent === 'exams')) return `${value}%`
    return String(value)
  }
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—'
  if (isRef(value)) return value.name
  if (key === 'date' && typeof value === 'string') return formatDate(value)
  return String(value)
}

function Rows({ data, parent }: { data: Record<string, unknown>; parent?: string }) {
  const entries = Object.entries(data).filter(
    ([key, value]) => !SKIP.has(key) && !(typeof value === 'object' && value !== null && !Array.isArray(value) && !isRef(value)),
  )
  if (!entries.length) return null
  return (
    <dl className="space-y-1.5">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-3 text-sm">
          <dt className="text-ink-secondary">{LABELS[key] ?? key}</dt>
          <dd className="text-right font-medium text-ink">{format(key, value, parent)}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * The report's LMS figures — computed by the backend from the Reports / KPI
 * engine and the test sessions, never typed in. Plain values go in the first
 * card; each nested group of figures gets its own.
 */
export function ReportMetrics({ metrics }: { metrics: Metrics }) {
  const sections = Object.entries(metrics).filter(
    ([key, value]) => !SKIP.has(key) && typeof value === 'object' && value !== null && !Array.isArray(value) && !isRef(value),
  ) as [string, Record<string, unknown>][]
  const hasPlain = Object.entries(metrics).some(([key, value]) => !SKIP.has(key) && !sections.some(([k]) => k === key) && value !== undefined)

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {hasPlain ? (
        <div className="rounded-xl border border-border bg-surface p-4">
          <h4 className="mb-2 text-sm font-semibold text-ink">Основное</h4>
          <Rows data={metrics} />
        </div>
      ) : null}
      {sections.map(([key, value]) => (
        <div key={key} className="rounded-xl border border-border bg-surface p-4">
          <h4 className="mb-2 text-sm font-semibold text-ink">{LABELS[key] ?? key}</h4>
          <Rows data={value} parent={key} />
        </div>
      ))}
    </div>
  )
}
