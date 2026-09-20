import type { AcademyReportTeacherRow } from '@/types/academyReport'
import { formatRuPercent } from '@/utils/format'

/** Plain per-teacher figures, neutral labels only — never a "best/worst
 * teacher" ranking or sort (spec: no subjective conclusions from one KPI). */
export function AcademyReportTeachersTable({ teachers }: { teachers: AcademyReportTeacherRow[] }) {
  if (teachers.length === 0) {
    return <p className="text-sm text-ink-muted">Нет данных за этот месяц.</p>
  }

  return (
    <>
      {/* Desktop: table */}
      <table className="hidden w-full text-sm sm:table">
        <thead>
          <tr className="border-b border-border text-left text-xs text-ink-secondary">
            <th className="pb-2 font-medium">Преподаватель</th>
            <th className="pb-2 font-medium">Занятия</th>
            <th className="pb-2 font-medium">Студенты</th>
            <th className="pb-2 font-medium">Посещаемость</th>
            <th className="pb-2 font-medium">KPI</th>
          </tr>
        </thead>
        <tbody>
          {teachers.map((teacher) => (
            <tr key={teacher.id} className="border-b border-border last:border-0">
              <td className="py-2.5 font-medium text-ink">{teacher.name}</td>
              <td className="py-2.5 text-ink-secondary">{teacher.lessons_completed}</td>
              <td className="py-2.5 text-ink-secondary">{teacher.students_count}</td>
              <td className="py-2.5 text-ink-secondary">{formatRuPercent(teacher.attendance_rate)}</td>
              <td className="py-2.5 text-ink-secondary">
                {teacher.kpi_total === null ? 'Нет данных' : formatRuPercent(teacher.kpi_total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Mobile: cards */}
      <div className="space-y-2 sm:hidden">
        {teachers.map((teacher) => (
          <div key={teacher.id} className="rounded-lg border border-border p-3">
            <p className="font-medium text-ink">{teacher.name}</p>
            <div className="mt-1.5 grid grid-cols-2 gap-y-1 text-sm text-ink-secondary">
              <span>{teacher.lessons_completed} занятий</span>
              <span>{teacher.students_count} студентов</span>
              <span>{formatRuPercent(teacher.attendance_rate)} посещаемость</span>
              <span>KPI: {teacher.kpi_total === null ? 'Нет данных' : formatRuPercent(teacher.kpi_total)}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
