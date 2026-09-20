import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { AcademyReportGroupRow } from '@/types/academyReport'
import { formatRuPercent } from '@/utils/format'

const STATUS_TONE: Record<AcademyReportGroupRow['status'], BadgeTone> = {
  active: 'success',
  paused: 'warning',
  completed: 'muted',
  cancelled: 'danger',
}

export function AcademyReportGroupsTable({ groups }: { groups: AcademyReportGroupRow[] }) {
  if (groups.length === 0) {
    return <p className="text-sm text-ink-muted">Нет данных за этот месяц.</p>
  }

  return (
    <>
      {/* Desktop: table */}
      <table className="hidden w-full text-sm sm:table">
        <thead>
          <tr className="border-b border-border text-left text-xs text-ink-secondary">
            <th className="pb-2 font-medium">Группа</th>
            <th className="pb-2 font-medium">Студенты</th>
            <th className="pb-2 font-medium">Занятия</th>
            <th className="pb-2 font-medium">Посещаемость</th>
            <th className="pb-2 font-medium">Статус</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group.id} className="border-b border-border last:border-0">
              <td className="py-2.5 font-medium text-ink">{group.name}</td>
              <td className="py-2.5 text-ink-secondary">{group.students_count}</td>
              <td className="py-2.5 text-ink-secondary">{group.lessons_count}</td>
              <td className="py-2.5 text-ink-secondary">{formatRuPercent(group.attendance_rate)}</td>
              <td className="py-2.5">
                <Badge tone={STATUS_TONE[group.status]}>{group.status_display}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Mobile: cards */}
      <div className="space-y-2 sm:hidden">
        {groups.map((group) => (
          <div key={group.id} className="rounded-lg border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium text-ink">{group.name}</p>
              <Badge tone={STATUS_TONE[group.status]}>{group.status_display}</Badge>
            </div>
            <div className="mt-1.5 flex justify-between text-sm text-ink-secondary">
              <span>{group.students_count} студентов</span>
              <span>{group.lessons_count} занятий</span>
              <span>{formatRuPercent(group.attendance_rate)}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
