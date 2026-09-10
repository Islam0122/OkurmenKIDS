import { Check, Clock, HeartHandshake, X } from 'lucide-react'

import type { AttendanceStatus } from '@/types/attendance'
import { cn } from '@/utils/cn'

const STATUS_CONTROLS: { value: AttendanceStatus; label: string; icon: typeof Check; activeClasses: string }[] = [
  { value: 'present', label: 'Был', icon: Check, activeClasses: 'bg-brand-500 text-white border-brand-500' },
  { value: 'absent', label: 'Не был', icon: X, activeClasses: 'bg-danger text-white border-danger' },
  { value: 'late', label: 'Опоздал', icon: Clock, activeClasses: 'bg-warning text-white border-warning' },
  { value: 'excused', label: 'Уваж.', icon: HeartHandshake, activeClasses: 'bg-ink-muted text-white border-ink-muted' },
]

export interface AttendanceRow {
  studentId: number
  studentName: string
  status: AttendanceStatus
}

export interface AttendanceTableProps {
  rows: AttendanceRow[]
  onStatusChange: (studentId: number, status: AttendanceStatus) => void
}

export function AttendanceTable({ rows, onStatusChange }: AttendanceTableProps) {
  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
      {rows.map((row) => (
        <li key={row.studentId} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="font-medium text-ink">{row.studentName}</span>
          <div role="radiogroup" aria-label={`Статус посещаемости для ${row.studentName}`} className="flex gap-1.5">
            {STATUS_CONTROLS.map((control) => {
              const isActive = row.status === control.value
              return (
                <button
                  key={control.value}
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  onClick={() => onStatusChange(row.studentId, control.value)}
                  className={cn(
                    'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors',
                    isActive ? control.activeClasses : 'border-border bg-surface text-ink-secondary hover:bg-surface-hover',
                  )}
                >
                  <control.icon className="size-3.5" aria-hidden />
                  {control.label}
                </button>
              )
            })}
          </div>
        </li>
      ))}
    </ul>
  )
}
