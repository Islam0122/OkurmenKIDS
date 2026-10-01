import { Phone } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { Student } from '@/types/academy'

export function StudentCard({ student }: { student: Student }) {
  return (
    <Link
      to={`/app/students/${student.id}`}
      className="flex items-center justify-between gap-3 card card-body card-interactive"
    >
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{student.full_name}</p>
        <p className="mt-0.5 truncate text-sm text-ink-secondary">{student.group_name ?? 'Без группы'}</p>
        {student.phone ? (
          <p className="mt-1 flex items-center gap-1 text-xs text-ink-muted">
            <Phone className="size-3" aria-hidden />
            {student.phone}
          </p>
        ) : null}
      </div>
      <Badge tone={student.is_active ? 'success' : 'muted'}>{student.is_active ? 'Активен' : 'Неактивен'}</Badge>
    </Link>
  )
}
