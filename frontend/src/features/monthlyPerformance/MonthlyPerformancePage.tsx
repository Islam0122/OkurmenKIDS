import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CalendarCheck,
  GraduationCap,
  Minus,
  NotebookPen,
  RefreshCw,
  Tv,
  Users,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import {
  monthlyPerformanceApi,
  type CorrectionPayload,
  type MonthlyPerformance,
  type PerformanceCard,
  type PerformanceDay,
  type PerformanceMetric,
} from '@/api/monthlyPerformance'
import logo from '@/assets/logo.png'
import { Header } from '@/components/layout/Header'
import { MobileNavigation } from '@/components/layout/MobileNavigation'
import { Sidebar } from '@/components/layout/Sidebar'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage } from '@/lib/apiError'
import { workspaceFor } from '@/features/staffAttendance/roles'
import type { UserRole } from '@/types/auth'
import { cn } from '@/utils/cn'

import { PerformanceChart } from './PerformanceChart'
import { MONTHS, dayMonthLabel, formatChange, formatCount, formatDateTime, formatPct } from './format'

export const MONTHLY_PERFORMANCE_PATH = '/dashboard/monthly-performance'
export const REFRESH_INTERVAL_MS = 5 * 60 * 1000
const PROJECT_TZ = 'Asia/Bishkek'

/** Роли, у которых есть общее меню LMS (/app) — страница открывается внутри него. */
const LMS_SHELL_ROLES: UserRole[] = ['admin', 'teacher', 'team_lead']

interface MetricDef {
  key: PerformanceMetric
  label: string
  cardLabel: string
  icon: LucideIcon
  percent: boolean
}

const METRICS: MetricDef[] = [
  { key: 'attendance_percent', label: 'Посещаемость', cardLabel: 'Посещаемость', icon: CalendarCheck, percent: true },
  { key: 'homework_percent', label: 'Домашние задания', cardLabel: 'Домашние задания', icon: NotebookPen, percent: true },
  { key: 'active_groups', label: 'Количество групп', cardLabel: 'Количество групп', icon: Users, percent: false },
  { key: 'active_students', label: 'Количество студентов', cardLabel: 'Количество студентов', icon: GraduationCap, percent: false },
]

function nowInProject(): { year: number; month: number } {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: PROJECT_TZ, year: 'numeric', month: 'numeric' }).formatToParts(new Date())
  return {
    year: Number(parts.find((p) => p.type === 'year')?.value),
    month: Number(parts.find((p) => p.type === 'month')?.value),
  }
}

function formatValue(value: number | null, percent: boolean): string {
  return percent ? formatPct(value) : formatCount(value)
}

// ---------------------------------------------------------------------------
// Страница
// ---------------------------------------------------------------------------

export function MonthlyPerformancePage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const tv = params.get('tv') === '1'
  const current = nowInProject()
  const year = Number(params.get('year')) || current.year
  const month = Number(params.get('month')) || current.month

  const query = useQuery({
    queryKey: ['monthly-performance', year, month],
    queryFn: () => monthlyPerformanceApi.month({ year, month }),
    refetchInterval: REFRESH_INTERVAL_MS,
    refetchIntervalInBackground: true,
    placeholderData: (previous) => previous,
  })

  const update = useCallback(
    (changes: Record<string, string | null>) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(changes)) {
          if (value === null) next.delete(key)
          else next.set(key, value)
        }
        return next
      }, { replace: true })
    },
    [setParams],
  )

  const enterTv = () => {
    update({ tv: '1' })
    document.documentElement.requestFullscreen?.().catch(() => undefined)
  }
  const exitTv = useCallback(() => {
    update({ tv: null })
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined)
  }, [update])

  useEffect(() => {
    if (!tv) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') exitTv()
    }
    // Браузер сам выходит из полноэкранного режима по Esc — выходим и из режима телевизора.
    let wasFullscreen = Boolean(document.fullscreenElement)
    const onFullscreen = () => {
      if (wasFullscreen && !document.fullscreenElement) exitTv()
      wasFullscreen = Boolean(document.fullscreenElement)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('fullscreenchange', onFullscreen)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('fullscreenchange', onFullscreen)
    }
  }, [tv, exitTv])

  const content = (
    <PerformanceContent
      tv={tv}
      year={year}
      month={month}
      query={query}
      onMonth={(y, m) => update({ year: String(y), month: String(m) })}
      onCurrent={() => update({ year: null, month: null })}
      onEnterTv={enterTv}
      onExitTv={exitTv}
    />
  )

  if (tv) {
    return (
      <div className="fixed inset-0 z-40 overflow-auto bg-surface" data-testid="tv-mode">
        {content}
      </div>
    )
  }
  return <Shell role={user?.role}>{content}</Shell>
}

/** Обычный режим: у тренеров, тимлида и администратора — меню LMS; у остальных
 * сотрудников — простая шапка с возвратом в свой кабинет. */
function Shell({ role, children }: { role: UserRole | undefined; children: ReactNode }) {
  if (role && LMS_SHELL_ROLES.includes(role)) {
    return (
      <div className="flex min-h-dvh bg-surface-muted">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="flex-1 pb-[calc(var(--spacing-mobile-nav)+env(safe-area-inset-bottom)+1.5rem)] lg:pb-8">
            <div className="mx-auto w-full max-w-page px-4 pt-6 sm:px-6 lg:px-8">{children}</div>
          </main>
        </div>
        <MobileNavigation />
      </div>
    )
  }
  // Роли без своего кабинета (ДОП, РОП, продажи) возвращаются к отметке прихода.
  const home = workspaceFor(role)?.to ?? '/attendance'
  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="sticky top-0 z-30 border-b border-border bg-surface">
        <div className="mx-auto flex h-header w-full max-w-page items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <img src={logo} alt="OkurmenKIDS" className="size-8 object-contain" />
            <span className="font-semibold text-ink">OkurmenKIDS</span>
          </div>
          <Link to={home} className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
            <ArrowLeft className="size-4" aria-hidden />
            В свой кабинет
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-page px-4 pt-6 pb-10 sm:px-6 lg:px-8">{children}</main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Содержимое (общий для обычного режима и режима телевизора)
// ---------------------------------------------------------------------------

interface ContentProps {
  tv: boolean
  year: number
  month: number
  query: ReturnType<typeof useQuery<MonthlyPerformance>>
  onMonth: (year: number, month: number) => void
  onCurrent: () => void
  onEnterTv: () => void
  onExitTv: () => void
}

function PerformanceContent({ tv, year, month, query, onMonth, onCurrent, onEnterTv, onExitTv }: ContentProps) {
  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = query
  const [editDay, setEditDay] = useState<PerformanceDay | null>(null)
  const current = nowInProject()
  const isCurrent = year === current.year && month === current.month
  const years = data?.available_years ?? [current.year]
  const monthOptions = MONTHS.map((label, index) => ({ value: String(index + 1), label }))
    .filter((option) => year < current.year || Number(option.value) <= current.month)

  return (
    <div className={cn(tv ? 'flex min-h-full flex-col gap-5 px-8 py-6' : 'space-y-6')}>
      {tv ? (
        <TvHeader monthLabel={`${MONTHS[month - 1]} ${year}`} onExit={onExitTv} />
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Общая статистика</h1>
            <p className="mt-1 text-sm text-ink-secondary">
              Последнее обновление: {dataUpdatedAt ? formatDateTime(new Date(dataUpdatedAt), PROJECT_TZ).time : '—'}
              {isFetching ? <RefreshCw className="ml-1.5 inline size-3.5 animate-spin" aria-label="Обновление" /> : null}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
              Выбрать месяц
              <Select
                aria-label="Месяц"
                className="w-36"
                value={String(month)}
                options={monthOptions}
                onChange={(event) => onMonth(year, Number(event.target.value))}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
              Год
              <Select
                aria-label="Год"
                className="w-28"
                value={String(year)}
                options={years.map((y) => ({ value: String(y), label: String(y) }))}
                onChange={(event) => {
                  const nextYear = Number(event.target.value)
                  onMonth(nextYear, nextYear === current.year ? Math.min(month, current.month) : month)
                }}
              />
            </label>
            <Button variant="secondary" onClick={onCurrent} disabled={isCurrent}>
              Текущий месяц
            </Button>
            <Button size="lg" leftIcon={<Tv className="size-5" aria-hidden />} onClick={onEnterTv}>
              Режим телевизора
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <LoadingState label="Загружаем статистику…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : (
        <>
          <div className={cn('grid gap-4', tv ? 'grid-cols-2 gap-5 lg:grid-cols-4' : 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4')}>
            {METRICS.map((metric) => (
              <KpiCard key={metric.key} metric={metric} card={data.summary[metric.key]} tv={tv} />
            ))}
          </div>
          <DailyTable data={data} tv={tv} onEdit={data.can_edit && !tv ? setEditDay : undefined} />
          <div>
            {!tv ? <h2 className="section-title mb-3">Динамика за месяц</h2> : null}
            <div className={cn('grid gap-4', tv ? 'grid-cols-1 gap-5 lg:grid-cols-2' : 'grid-cols-1 xl:grid-cols-2')}>
              <PerformanceChart
                title="Посещаемость"
                points={data.trends.attendance.points}
                daysInMonth={data.days.length}
                average={data.trends.attendance.average}
                tv={tv}
              />
              <PerformanceChart
                title="Домашние задания"
                points={data.trends.homework.points}
                daysInMonth={data.days.length}
                average={data.trends.homework.average}
                tv={tv}
              />
            </div>
          </div>
          {tv ? (
            <p className="-mt-2 text-right text-lg text-ink-muted">
              Последнее обновление: {formatDateTime(new Date(dataUpdatedAt), PROJECT_TZ).time} · обновляется каждые 5 минут
            </p>
          ) : null}
        </>
      )}

      {editDay && data ? (
        <CorrectionModal day={editDay} year={data.year} month={data.month} onClose={() => setEditDay(null)} />
      ) : null}
    </div>
  )
}

function TvHeader({ monthLabel, onExit }: { monthLabel: string; onExit: () => void }) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const { date, time } = formatDateTime(now, PROJECT_TZ)
  return (
    <div className="flex items-center justify-between gap-6">
      <div className="flex items-center gap-4">
        <img src={logo} alt="OkurmenKIDS" className="size-14 object-contain" />
        <div>
          <h1 className="text-4xl font-bold text-ink xl:text-5xl">Общая статистика</h1>
          <p className="mt-1 text-2xl text-brand-700">{monthLabel}</p>
        </div>
      </div>
      <div className="flex items-center gap-6">
        <div className="text-right">
          <p className="text-5xl font-bold tabular-nums text-ink xl:text-6xl" data-testid="tv-clock">{time}</p>
          <p className="mt-1 text-xl text-ink-secondary">{date}</p>
        </div>
        <button
          type="button"
          onClick={onExit}
          className="flex size-12 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover hover:text-ink"
          aria-label="Выйти из режима телевизора (Esc)"
          title="Выйти (Esc)"
        >
          <X className="size-7" aria-hidden />
        </button>
      </div>
    </div>
  )
}

function KpiCard({ metric, card, tv }: { metric: MetricDef; card: PerformanceCard; tv: boolean }) {
  const change = card.change
  const trend = change === null ? null : change > 0 ? 'up' : change < 0 ? 'down' : 'flat'
  const TrendIcon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : trend === 'flat' ? Minus : ArrowRight
  return (
    <div className={cn('card flex flex-col justify-between border-t-4 border-t-brand-500', tv ? 'gap-3 px-6 py-5' : 'gap-3 p-5')}>
      <div className="flex items-center justify-between gap-2">
        <span className={cn('font-medium text-ink-secondary', tv ? 'text-2xl' : 'text-sm')}>{metric.cardLabel}</span>
        <span className={cn('flex items-center justify-center rounded-xl bg-brand-50 text-brand-700', tv ? 'size-14' : 'size-10')}>
          <metric.icon className={tv ? 'size-8' : 'size-5'} aria-hidden />
        </span>
      </div>
      <div>
        <p className={cn('font-bold tabular-nums leading-none text-ink', tv ? 'text-6xl xl:text-7xl' : 'text-4xl')}>
          {formatValue(card.value, metric.percent)}
        </p>
        <p className={cn('mt-2 text-ink-muted', tv ? 'text-xl' : 'text-xs')}>
          {card.date ? dayMonthLabel(card.date) : 'Нет данных'}
          {metric.percent && card.month_average !== undefined && card.month_average !== null
            ? ` · за месяц ${formatPct(card.month_average)}`
            : ''}
        </p>
      </div>
      <div
        className={cn(
          'flex items-center gap-1.5 font-medium',
          tv ? 'text-2xl' : 'text-sm',
          trend === 'up' ? 'text-brand-700' : trend === 'down' ? 'text-danger' : 'text-ink-muted',
        )}
      >
        <TrendIcon className={tv ? 'size-7' : 'size-4'} aria-hidden />
        <span>
          Изменение за день: {change === null ? '—' : formatChange(change, metric.percent)}
        </span>
      </div>
    </div>
  )
}

function DailyTable({ data, tv, onEdit }: { data: MonthlyPerformance; tv: boolean; onEdit?: (day: PerformanceDay) => void }) {
  const cell = tv ? 'px-0.5 py-2.5 text-lg xl:text-xl' : 'px-2 py-2.5 text-sm'
  return (
    <section className="card min-w-0 overflow-hidden" aria-label="Показатели по дням">
      <div className={cn(tv ? 'overflow-hidden' : 'overflow-x-auto')}>
        <table className={cn('w-full border-collapse text-center tabular-nums', tv && 'table-fixed')}>
          <thead>
            <tr className="border-b border-border bg-surface-muted">
              <th scope="col" className={cn('sticky left-0 z-10 bg-surface-muted text-left font-semibold text-ink', tv ? 'w-[18rem] px-4 py-2.5 text-2xl' : 'min-w-44 px-4 py-2.5 text-sm')}>
                {data.month_label}
              </th>
              {data.days.map((day) => {
                const weekend = day.weekday >= 6
                const editable = onEdit && !day.is_future
                return (
                  <th
                    key={day.date}
                    scope="col"
                    className={cn(
                      'font-semibold',
                      cell,
                      !tv && 'min-w-12',
                      day.is_today ? 'bg-brand-500 text-white' : weekend ? 'text-ink-muted' : 'text-ink-secondary',
                      day.is_future && 'opacity-50',
                    )}
                  >
                    {editable ? (
                      <button
                        type="button"
                        onClick={() => onEdit(day)}
                        className="rounded px-1 underline decoration-dotted underline-offset-4 hover:text-brand-700"
                        title="Скорректировать показатели"
                      >
                        {day.day}
                      </button>
                    ) : (
                      day.day
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {METRICS.map((metric) => (
              <tr key={metric.key} className="border-b border-border last:border-0">
                <th scope="row" className={cn('sticky left-0 z-10 whitespace-nowrap bg-surface text-left font-medium text-ink', tv ? 'px-4 py-2.5 text-xl xl:text-2xl' : 'px-4 py-2.5 text-sm')}>
                  {metric.label}
                </th>
                {data.days.map((day) => {
                  const value = day[metric.key]
                  const manual = day.manual_fields.includes(metric.key)
                  return (
                    <td
                      key={day.date}
                      className={cn(
                        cell,
                        day.is_today && 'bg-brand-50 font-semibold',
                        value === null ? 'text-ink-muted' : 'text-ink',
                      )}
                      title={manual ? `Скорректировано вручную${day.manual_comment ? `: ${day.manual_comment}` : ''}` : undefined}
                    >
                      {day.is_future ? '' : metric.percent && value !== null ? `${Math.round(value)}%` : formatCount(value)}
                      {manual ? <sup className="text-brand-700">*</sup> : null}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!tv ? (
        <p className="border-t border-border px-4 py-2 text-xs text-ink-muted">
          «—» — нет данных · * — скорректировано вручную
          {onEdit ? ' · нажмите на число дня, чтобы скорректировать' : ''}
        </p>
      ) : null}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Ручная корректировка (только сотрудники с правом — проверяет backend)
// ---------------------------------------------------------------------------

function CorrectionModal({ day, year, month, onClose }: { day: PerformanceDay; year: number; month: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<PerformanceMetric, string>>(() => ({
    attendance_percent: day.attendance_percent === null ? '' : String(day.attendance_percent),
    homework_percent: day.homework_percent === null ? '' : String(day.homework_percent),
    active_groups: day.active_groups === null ? '' : String(day.active_groups),
    active_students: day.active_students === null ? '' : String(day.active_students),
  }))
  const [comment, setComment] = useState(day.manual_comment)

  const initial = (key: PerformanceMetric) => (day[key] === null ? '' : String(day[key]))
  const mutation = useMutation({
    mutationFn: (payload: CorrectionPayload) => monthlyPerformanceApi.correct(day.date, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['monthly-performance', year, month] })
      onClose()
    },
  })

  const submit = () => {
    const payload: CorrectionPayload = { comment }
    for (const metric of METRICS) {
      const raw = values[metric.key].trim().replace(',', '.')
      if (raw === initial(metric.key)) continue
      payload[metric.key] = raw === '' ? null : Number(raw)
    }
    mutation.mutate(payload)
  }

  return (
    <Modal isOpen onClose={onClose} title={`Корректировка за ${dayMonthLabel(day.date)}`}>
      <form
        className="space-y-4 px-4 pb-4 sm:px-6 sm:pb-6"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        {METRICS.map((metric) => (
          <label key={metric.key} className="flex flex-col gap-1 text-sm font-medium text-ink">
            {metric.label}
            {metric.percent ? ', %' : ''}
            <Input
              inputMode="decimal"
              value={values[metric.key]}
              placeholder="Нет данных"
              onChange={(event) => setValues((prev) => ({ ...prev, [metric.key]: event.target.value }))}
            />
          </label>
        ))}
        <label className="flex flex-col gap-1 text-sm font-medium text-ink">
          Комментарий
          <Input value={comment} maxLength={255} onChange={(event) => setComment(event.target.value)} />
        </label>
        {mutation.isError ? (
          <p className="text-sm text-danger" role="alert">{extractErrorMessage(mutation.error)}</p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
          <Button type="submit" isLoading={mutation.isPending}>Сохранить</Button>
        </div>
      </form>
    </Modal>
  )
}
