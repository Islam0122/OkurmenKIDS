import type { MonthlyReportGroupRow } from '@/types/monthlyReport'

export function ReportGroupsTable({ groups }: { groups: MonthlyReportGroupRow[] }) {
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
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group.id} className="border-b border-border last:border-0">
              <td className="py-2.5 font-medium text-ink">{group.name}</td>
              <td className="py-2.5 text-ink-secondary">{group.students_count}</td>
              <td className="py-2.5 text-ink-secondary">{group.lessons_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Mobile: cards */}
      <div className="space-y-2 sm:hidden">
        {groups.map((group) => (
          <div key={group.id} className="rounded-lg border border-border p-3">
            <p className="font-medium text-ink">{group.name}</p>
            <div className="mt-1.5 flex justify-between text-sm text-ink-secondary">
              <span>{group.students_count} студентов</span>
              <span>{group.lessons_count} занятий</span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
