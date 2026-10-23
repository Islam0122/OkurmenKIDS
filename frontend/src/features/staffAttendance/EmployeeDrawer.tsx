import { useState } from 'react'
import { PencilLine } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Drawer } from '@/components/ui/Drawer'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useEmployeeAttendance } from '@/hooks/useStaffAttendance'
import { extractErrorMessage } from '@/lib/apiError'
import type { Adjustment, Employee, SessionSnapshot, WorkSession } from '@/types/staffAttendance'

import { DAY_STATUS_TONE } from './statusUi'
import { formatDateTime, formatDay, formatDistance, formatDuration, formatLate, formatTime, shiftDay } from './format'
import { Avatar, SESSION_TONE } from './PersonalAttendancePage'

interface Props {
  employeeId: number | null
  today: string
  timeZone: string
  canAdjust: boolean
  onClose: () => void
  onAdjust: (employee: Employee, session: WorkSession) => void
}

/** Карточка сотрудника: история за период, все события, исправления и их причины. */
export function EmployeeDrawer({ employeeId, today, timeZone, canAdjust, onClose, onAdjust }: Props) {
  const [dateFrom, setDateFrom] = useState(shiftDay(today, -30))
  const [dateTo, setDateTo] = useState(today)
  const card = useEmployeeAttendance(employeeId, { date_from: dateFrom, date_to: dateTo })
  const data = card.data

  return (
    <Drawer isOpen={employeeId !== null} onClose={onClose} title={data?.employee.full_name ?? 'Сотрудник'} side="right" size="lg">
      {card.isPending ? (
        <LoadingState />
      ) : card.isError ? (
        <ErrorState message={extractErrorMessage(card.error)} onRetry={() => void card.refetch()} />
      ) : data ? (
        <div className="space-y-5">
          <div className="flex items-center gap-3">
            <Avatar employee={data.employee} />
            <div className="min-w-0">
              <p className="truncate font-semibold text-ink">{data.employee.full_name}</p>
              <p className="text-sm text-ink-secondary">{data.employee.role_label} · {data.employee.username}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="emp-from" className="mb-1.5 block field-label">С</label>
              <DatePicker id="emp-from" value={dateFrom} max={dateTo} onChange={(e) => e.target.value && setDateFrom(e.target.value)} />
            </div>
            <div>
              <label htmlFor="emp-to" className="mb-1.5 block field-label">По</label>
              <DatePicker id="emp-to" value={dateTo} min={dateFrom} onChange={(e) => e.target.value && setDateTo(e.target.value)} />
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {[
              ['Дней на работе', String(data.stats.days_present)],
              ['Опозданий', `${data.stats.late_days} (${formatLate(data.stats.late_minutes_total)})`],
              ['Общее время', formatDuration(data.stats.total_seconds)],
              ['Нет прихода', String(data.stats.no_check_in_days)],
              ['Нет ухода', String(data.stats.no_check_out_days)],
              ['Исправлений', String(data.adjustments.length)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-surface-muted px-3 py-2">
                <dt className="text-xs text-ink-secondary">{label}</dt>
                <dd className="text-sm font-semibold text-ink">{value}</dd>
              </div>
            ))}
          </dl>

          <section aria-label="История по дням">
            <h3 className="section-title mb-2">История по дням</h3>
            {data.days.length === 0 ? (
              <p className="text-sm text-ink-secondary">За период нет отметок.</p>
            ) : (
              <ul className="space-y-2">
                {data.days.map((row) => (
                  <li key={row.key} className="rounded-xl border border-border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium text-ink">{formatDay(row.date)}</p>
                      <div className="flex flex-wrap gap-1">
                        {row.is_late ? <Badge tone="warning">Опоздание {formatLate(row.late_minutes)}</Badge> : null}
                        {row.is_adjusted ? <Badge tone="info">Исправлено</Badge> : null}
                        <Badge tone={DAY_STATUS_TONE[row.status]}>{row.status_label}</Badge>
                      </div>
                    </div>
                    {row.sessions.map((s) => (
                      <div key={s.id} className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="tabular-nums text-ink-secondary">
                          {formatTime(s.checked_in_at, timeZone)} — {s.checked_out_at ? formatTime(s.checked_out_at, timeZone) : s.status === 'open' ? 'на работе' : 'нет ухода'}
                          {' · '}{formatDuration(s.duration_seconds)}
                          {s.location ? ` · ${s.location.name}` : ''}
                          {s.check_in_distance_m !== null ? ` · ${formatDistance(s.check_in_distance_m)} от центра` : ''}
                          {s.source === 'manual' ? ' · вручную' : ''}
                        </span>
                        <span className="flex items-center gap-1">
                          <Badge tone={SESSION_TONE[s.status]}>{s.status_label}</Badge>
                          {canAdjust ? (
                            <Button size="sm" variant="ghost" aria-label="Исправить сессию" onClick={() => onAdjust(data.employee, s)}>
                              <PencilLine className="size-4" aria-hidden />
                            </Button>
                          ) : null}
                        </span>
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Исправления">
            <h3 className="section-title mb-2">Исправления</h3>
            {data.adjustments.length === 0 ? (
              <p className="text-sm text-ink-secondary">Ручных исправлений не было.</p>
            ) : (
              <ul className="space-y-2">
                {data.adjustments.map((a) => <AdjustmentItem key={a.id} adjustment={a} timeZone={timeZone} />)}
              </ul>
            )}
          </section>

          <section aria-label="Журнал отметок">
            <h3 className="section-title mb-2">Все события отметок</h3>
            {data.events.length === 0 ? (
              <p className="text-sm text-ink-secondary">Событий нет.</p>
            ) : (
              <ul className="divide-y divide-border rounded-xl border border-border text-sm">
                {data.events.map((e) => (
                  <li key={e.id} className="flex flex-wrap justify-between gap-2 px-3 py-2">
                    <span className="font-medium text-ink">{e.kind_label}</span>
                    <span className="tabular-nums text-ink-secondary">
                      {formatDateTime(e.occurred_at, timeZone)}
                      {e.location_name ? ` · ${e.location_name}` : ''}
                      {e.distance_m !== null ? ` · ${formatDistance(e.distance_m)}` : ''}
                      {e.accuracy_m !== null ? ` · ±${Math.round(e.accuracy_m)} м` : ''}
                      {e.created_by_name ? ` · ${e.created_by_name}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </Drawer>
  )
}

function snapshotText(values: SessionSnapshot, timeZone: string): string {
  if (!values.checked_in_at) return 'нет записи'
  const out = values.checked_out_at ? formatTime(values.checked_out_at, timeZone) : 'без ухода'
  const late = values.late_minutes ? `, опоздание ${values.late_minutes} мин` : ''
  return `${formatDateTime(values.checked_in_at, timeZone)} — ${out}${late}`
}

function AdjustmentItem({ adjustment, timeZone }: { adjustment: Adjustment; timeZone: string }) {
  return (
    <li className="rounded-xl border border-border p-3 text-sm">
      <div className="flex flex-wrap justify-between gap-2">
        <span className="font-medium text-ink">{adjustment.action_label}</span>
        <span className="text-ink-secondary">{adjustment.adjusted_by_name} · {formatDateTime(adjustment.created_at, timeZone)}</span>
      </div>
      <p className="mt-1 text-ink-secondary">Было: {snapshotText(adjustment.old_values, timeZone)}</p>
      <p className="text-ink-secondary">Стало: {snapshotText(adjustment.new_values, timeZone)}</p>
      <p className="mt-1 text-ink">Причина: {adjustment.reason}</p>
    </li>
  )
}
