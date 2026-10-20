import type { AcademyReportTeacherRow } from '@/types/academyReport'
import { formatRuPercent } from '@/utils/format'

/** The five KPI criteria of a teacher row (services.kpi_engine), in table order. */
const CRITERIA: { key: keyof AcademyReportTeacherRow; label: string }[] = [
  { key: 'attendance_rate', label: 'Посещаемость' },
  { key: 'homework_rate', label: 'ДЗ' },
  { key: 'progress_rate', label: 'Прогресс' },
  { key: 'activity_rate', label: 'Активность' },
  { key: 'test_score_rate', label: 'Результаты тестов' },
]

/** «Нет данных» for a criterion without data this month — never a fabricated 0%. */
function percentOrNoData(value: number | string | null): string {
  return typeof value === 'number' ? formatRuPercent(value) : 'Нет данных'
}

/** Plain per-teacher figures, neutral labels only — never a "best/worst
 * teacher" ranking or sort (spec: no subjective conclusions from one KPI). */
export function AcademyReportTeachersTable({ teachers }: { teachers: AcademyReportTeacherRow[] }) {
  if (teachers.length === 0) {
    return <p className="text-sm text-ink-muted">Нет данных за этот месяц.</p>
  }

  return (
    <>
      {/* Desktop: table */}
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-ink-secondary">
              <th className="pb-2 pr-3 font-medium">Преподаватель</th>
              <th className="pb-2 pr-3 font-medium">Занятия</th>
              <th className="pb-2 pr-3 font-medium">Студенты</th>
              {CRITERIA.map((criterion) => (
                <th key={criterion.key} className="pb-2 pr-3 font-medium">
                  {criterion.label}
                </th>
              ))}
              <th className="pb-2 font-medium">KPI</th>
            </tr>
          </thead>
          <tbody>
            {teachers.map((teacher) => (
              <tr key={teacher.id} className="border-b border-border last:border-0">
                <td className="py-2.5 pr-3 font-medium text-ink">{teacher.name}</td>
                <td className="py-2.5 pr-3 text-ink-secondary">{teacher.lessons_completed}</td>
                <td className="py-2.5 pr-3 text-ink-secondary">{teacher.students_count}</td>
                {CRITERIA.map((criterion) => (
                  <td key={criterion.key} className="py-2.5 pr-3 text-ink-secondary">
                    {percentOrNoData(teacher[criterion.key])}
                  </td>
                ))}
                <td className="py-2.5 text-ink-secondary">{percentOrNoData(teacher.kpi_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: cards */}
      <div className="space-y-2 sm:hidden">
        {teachers.map((teacher) => (
          <div key={teacher.id} className="rounded-lg border border-border p-3">
            <p className="font-medium text-ink">{teacher.name}</p>
            <div className="mt-1.5 grid grid-cols-2 gap-y-1 text-sm text-ink-secondary">
              <span>{teacher.lessons_completed} занятий</span>
              <span>{teacher.students_count} студентов</span>
              {CRITERIA.map((criterion) => (
                <span key={criterion.key}>
                  {criterion.label}: {percentOrNoData(teacher[criterion.key])}
                </span>
              ))}
              <span>KPI: {percentOrNoData(teacher.kpi_total)}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
