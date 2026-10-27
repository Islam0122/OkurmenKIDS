import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CalendarClock, Construction, ChevronLeft, ChevronRight, Clock3, LogIn, LogOut, ScanLine, Timer, TrendingDown } from 'lucide-react'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useMyAttendanceHistory, useMyAttendanceStats, useMyAttendanceStatus } from '@/hooks/useStaffAttendance'
import { extractErrorMessage } from '@/lib/apiError'
import { resolveMediaUrl } from '@/lib/mediaUrl'
import type { Employee, MarkKind, MyStatus, WorkSession, WorkdayState } from '@/types/staffAttendance'

import {
  DEFAULT_TZ,
  formatClock,
  formatDay,
  formatDuration,
  formatLate,
  formatLongDate,
  formatMonth,
  formatTime,
  shiftMonth,
  zonedToday,
} from './format'
import { MarkFlow } from './MarkFlow'
import { VARIANT_TITLE, type PersonalVariant } from './roles'

const STATE_BADGE: Record<WorkdayState, { label: string; tone: BadgeTone }> = {
  not_arrived: { label: 'Ещё не пришёл', tone: 'muted' },
  at_work: { label: 'На работе', tone: 'success' },
  day_finished: { label: 'Рабочий день завершён', tone: 'info' },
}

export const SESSION_TONE: Record<WorkSession['status'], BadgeTone> = {
  open: 'success',
  closed: 'muted',
  missing_checkout: 'danger',
}

export function Avatar({ employee, size = 'lg' }: { employee: Employee; size?: 'md' | 'lg' }) {
  const photo = resolveMediaUrl(employee.photo_url)
  const initials = employee.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join('')
    .toUpperCase()
  const box = size === 'lg' ? 'size-16 text-xl' : 'size-9 text-sm'
  return photo ? (
    <img src={photo} alt={employee.full_name} className={`${box} shrink-0 rounded-full object-cover`} />
  ) : (
    <span className={`${box} flex shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-700`} aria-hidden>
      {initials}
    </span>
  )
}

/** Часы офиса: время сервера плюс прошедшее локально (часы устройства для
 * отображения не используются как источник истины). */
function useOfficeClock(serverTime: string | undefined): Date {
  const [now, setNow] = useState(() => new Date())
  const offset = useMemo(() => (serverTime ? new Date(serverTime).getTime() - Date.now() : 0), [serverTime])
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  return new Date(now.getTime() + offset)
}

export function PersonalAttendancePage({ variant, presetCode, onFlowDone, cabinetNotice = variant === 'staff' }: {
  variant: PersonalVariant
  presetCode?: string
  onFlowDone?: () => void
  /** «Ваш личный кабинет находится в разработке» — для ролей без своего кабинета. */
  cabinetNotice?: boolean
}) {
  const status = useMyAttendanceStatus()
  const [flowOpen, setFlowOpen] = useState(Boolean(presetCode))
  // Действие фиксируется при открытии: после отметки статус обновится, а
  // окно должно остаться про ту отметку, которую делали.
  const [flowAction, setFlowAction] = useState<MarkKind | null>(null)
  const nextAction = status.data?.next_action
  useEffect(() => {
    if (flowOpen && flowAction === null && nextAction) setFlowAction(nextAction)
  }, [flowOpen, flowAction, nextAction])

  if (status.isPending) return <LoadingState label="Загружаем ваш рабочий день…" />
  if (status.isError) return <ErrorState title="Не удалось загрузить данные" message={extractErrorMessage(status.error)} onRetry={() => void status.refetch()} />

  const data = status.data
  const action = flowAction ?? data.next_action
  const closeFlow = () => {
    setFlowOpen(false)
    setFlowAction(null)
    onFlowDone?.()
  }

  return (
    <div className="space-y-5">
      {cabinetNotice ? (
        <Card>
          <div role="status" className="flex items-center gap-3">
            <Construction className="size-5 shrink-0 text-brand-600" aria-hidden />
            <p className="text-sm font-medium text-ink">Ваш личный кабинет находится в разработке</p>
          </div>
        </Card>
      ) : null}
      <TodayCard
        status={data}
        variant={variant}
        onScan={() => {
          setFlowAction(data.next_action)
          setFlowOpen(true)
        }}
      />
      <MonthStatsSection timeZone={data.timezone} />
      <HistorySection timeZone={data.timezone} />
      <Modal
        isOpen={flowOpen}
        onClose={closeFlow}
        title={action === 'check_in' ? 'Отметить приход' : 'Отметить уход'}
        icon={<ScanLine className="size-5 text-brand-600" aria-hidden />}
      >
        {flowOpen ? <MarkFlow action={action} presetCode={presetCode} onDone={closeFlow} /> : null}
      </Modal>
    </div>
  )
}

function TodayCard({ status, variant, onScan }: { status: MyStatus; variant: PersonalVariant; onScan: () => void }) {
  const tz = status.timezone || DEFAULT_TZ
  const clock = useOfficeClock(status.server_time)
  const badge = STATE_BADGE[status.state]
  const today = status.today
  const isCheckIn = status.next_action === 'check_in'

  return (
    <Card>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-4">
          <Avatar employee={status.employee} />
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{VARIANT_TITLE[variant]}</p>
            <h1 className="truncate text-xl font-semibold text-ink">{status.employee.full_name}</h1>
            <p className="text-sm text-ink-secondary">{status.employee.role_label}</p>
          </div>
        </div>
        <div className="text-left lg:text-right">
          <p className="text-3xl font-semibold tabular-nums text-ink" aria-live="off">{formatClock(clock, tz)}</p>
          <p className="text-sm text-ink-secondary">{formatLongDate(clock, tz)}</p>
        </div>
      </div>

      {status.stale_session ? (
        <p className="mt-4 flex items-start gap-2 rounded-xl bg-warning-soft px-3 py-2 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          Уход за {formatDay(status.stale_session.work_date, false)} не был отмечен. Отметьте приход за сегодня — прошлую смену исправит администратор.
        </p>
      ) : null}

      <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl bg-surface-muted px-3 py-2.5">
            <dt className="text-xs text-ink-secondary">Статус</dt>
            <dd className="mt-1"><Badge tone={badge.tone}>{badge.label}</Badge></dd>
          </div>
          <div className="rounded-xl bg-surface-muted px-3 py-2.5">
            <dt className="flex items-center gap-1 text-xs text-ink-secondary"><LogIn className="size-3.5" aria-hidden />Приход</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums text-ink">{formatTime(today.check_in, tz)}</dd>
          </div>
          <div className="rounded-xl bg-surface-muted px-3 py-2.5">
            <dt className="flex items-center gap-1 text-xs text-ink-secondary"><LogOut className="size-3.5" aria-hidden />Уход</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums text-ink">{formatTime(today.check_out, tz)}</dd>
          </div>
          <div className="rounded-xl bg-surface-muted px-3 py-2.5">
            <dt className="flex items-center gap-1 text-xs text-ink-secondary"><Timer className="size-3.5" aria-hidden />Время на работе</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums text-ink">{formatDuration(today.duration_seconds)}</dd>
          </div>
        </dl>
        <Button size="lg" className="h-16 w-full px-8 text-lg lg:w-auto" onClick={onScan}>
          <span aria-hidden>📷</span> Сканировать QR
        </Button>
      </div>
      <p className="mt-3 text-sm text-ink-secondary">
        {isCheckIn ? 'Следующая отметка — приход.' : 'Следующая отметка — уход.'}
        {today.expected_start ? ` Начало рабочего дня: ${formatTime(today.expected_start, tz)}.` : ' Сегодня по расписанию нерабочий день.'}
        {today.is_late ? <span className="font-medium text-warning"> Опоздание: {formatLate(today.late_minutes)}.</span> : null}
      </p>
    </Card>
  )
}

function MonthStatsSection({ timeZone }: { timeZone: string }) {
  const currentMonth = zonedToday(timeZone).slice(0, 7)
  const [month, setMonth] = useState(currentMonth)
  const stats = useMyAttendanceStats(month)

  return (
    <section aria-label="Статистика за месяц" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="section-title">Статистика за месяц</h2>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" aria-label="Предыдущий месяц" onClick={() => setMonth(shiftMonth(month, -1))}>
            <ChevronLeft className="size-4" aria-hidden />
          </Button>
          <span className="min-w-36 text-center text-sm font-medium text-ink">{formatMonth(month)}</span>
          <Button variant="ghost" size="sm" aria-label="Следующий месяц" disabled={month >= currentMonth} onClick={() => setMonth(shiftMonth(month, 1))}>
            <ChevronRight className="size-4" aria-hidden />
          </Button>
        </div>
      </div>
      {stats.isError ? (
        <ErrorState title="Статистика недоступна" message={extractErrorMessage(stats.error)} onRetry={() => void stats.refetch()} />
      ) : (
        <StatGrid>
          <StatCard label="Дней на работе" value={stats.data ? `${stats.data.days_present} из ${stats.data.work_days}` : '…'} icon={CalendarClock} hint="Рабочих дней по расписанию — до сегодня" />
          <StatCard label="Опоздания" value={stats.data?.late_days ?? '…'} icon={TrendingDown} tone={stats.data && stats.data.late_days > 0 ? 'warning' : 'default'} hint={stats.data ? `Всего ${formatLate(stats.data.late_minutes_total)}` : undefined} />
          <StatCard label="Время на работе" value={stats.data ? formatDuration(stats.data.total_seconds) : '…'} icon={Clock3} hint={stats.data ? `В среднем ${formatDuration(stats.data.average_seconds)} в день` : undefined} />
          <StatCard label="Без отметки" value={stats.data ? stats.data.no_check_in_days + stats.data.no_check_out_days : '…'} icon={AlertTriangle} tone={stats.data && stats.data.no_check_in_days + stats.data.no_check_out_days > 0 ? 'danger' : 'default'} hint={stats.data ? `Нет прихода: ${stats.data.no_check_in_days}, нет ухода: ${stats.data.no_check_out_days}` : undefined} />
        </StatGrid>
      )}
      <p className="text-xs text-ink-muted">Продолжительность — время между приходом и уходом; это не расчёт оплачиваемых часов.</p>
    </section>
  )
}

function HistorySection({ timeZone }: { timeZone: string }) {
  const [page, setPage] = useState(1)
  const history = useMyAttendanceHistory({ page })

  return (
    <Card title="История посещений" description="Последние 31 день" padding="none">
      {history.isPending ? (
        <LoadingState />
      ) : history.isError ? (
        <ErrorState title="История недоступна" message={extractErrorMessage(history.error)} onRetry={() => void history.refetch()} />
      ) : history.data.results.length === 0 ? (
        <EmptyState title="Отметок пока нет" description="Отсканируйте QR-код офиса, чтобы отметить приход." />
      ) : (
        <>
          <ul className="divide-y divide-border">
            {history.data.results.map((session) => (
              <li key={session.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{formatDay(session.work_date)}</p>
                  <p className="text-sm tabular-nums text-ink-secondary">
                    {formatTime(session.checked_in_at, timeZone)} — {session.checked_out_at ? formatTime(session.checked_out_at, timeZone) : session.status === 'open' ? 'сейчас' : 'нет ухода'}
                    {session.location ? ` · ${session.location.name}` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium tabular-nums text-ink">{formatDuration(session.duration_seconds)}</span>
                  {session.late_minutes > 0 ? <Badge tone="warning">Опоздание {formatLate(session.late_minutes)}</Badge> : null}
                  {session.is_adjusted ? <Badge tone="info">Исправлено</Badge> : null}
                  <Badge tone={SESSION_TONE[session.status]}>{session.status_label}</Badge>
                </div>
              </li>
            ))}
          </ul>
          <div className="px-4 pb-4 sm:px-6">
            <Pagination page={page} pageSize={20} totalCount={history.data.count} onPageChange={setPage} />
          </div>
        </>
      )}
    </Card>
  )
}
