import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { Group } from '@/types/academy'
import { DAY_LABELS, WEEKDAY_ORDER } from '@/types/common'

const STATUS_TONE: Record<Group['status'], BadgeTone> = {
  active: 'success',
  paused: 'warning',
  completed: 'muted',
  cancelled: 'danger',
}

export function GroupCard({ group }: { group: Group }) {
  const activeSlots = group.schedules.filter((slot) => slot.is_active)
  const activeDays = WEEKDAY_ORDER.filter((day) => activeSlots.some((slot) => slot.day_of_week === day))
  const activePrograms = group.teachers.filter((program) => program.is_active).length

  return (
    <Link
      to={`/app/groups/${group.id}`}
      className="block rounded-xl border border-border bg-surface p-5 transition-colors hover:border-brand-200 hover:bg-brand-50/30"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-ink">{group.name}</h3>
        <Badge tone={STATUS_TONE[group.status]}>{group.status_display}</Badge>
      </div>
      <p className="mt-1 text-sm text-ink-secondary">{group.course_name}</p>

      <dl className="mt-4 space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-ink-secondary">Студенты</dt>
          <dd className="font-medium text-ink">
            {group.students_count}
            {group.max_students ? ` / ${group.max_students}` : ''}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-secondary">Учебные программы</dt>
          <dd className="font-medium text-ink">{activePrograms || '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-secondary">Дни занятий</dt>
          <dd className="font-medium text-ink">{activeDays.length ? activeDays.map((day) => DAY_LABELS[day]).join(' / ') : '—'}</dd>
        </div>
      </dl>
    </Link>
  )
}
