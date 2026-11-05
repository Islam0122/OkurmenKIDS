import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarCheck,
  GraduationCap,
  Minus,
  NotebookPen,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import {
  monthlyPerformanceApi,
  type CorrectionPayload,
  type MonthlyPerformance,
  type PerformanceCard,
  type PerformanceDay,
  type PerformanceMetric,
} from '@/api/monthlyPerformance'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { dayMonthLabel, formatChange, formatCount, formatPct } from './format'

export interface MetricDef {
  key: PerformanceMetric
  /** Подпись строки таблицы. */
  label: string
  /** Заголовок карточки. */
  cardLabel: string
  icon: LucideIcon
  percent: boolean
}

export const METRICS: MetricDef[] = [
  { key: 'attendance_percent', label: 'Посещаемость (%)', cardLabel: 'Посещаемость', icon: CalendarCheck, percent: true },
  { key: 'homework_percent', label: 'Домашние задания (%)', cardLabel: 'Выполнение домашних заданий', icon: NotebookPen, percent: true },
  { key: 'active_groups', label: 'Количество групп', cardLabel: 'Активные группы', icon: Users, percent: false },
  { key: 'active_students', label: 'Количество студентов', cardLabel: 'Активные студенты', icon: GraduationCap, percent: false },
]

export function formatValue(value: number | null, percent: boolean): string {
  return percent ? formatPct(value) : formatCount(value)
}

// ---------------------------------------------------------------------------
// Карточка показателя
// ---------------------------------------------------------------------------

export function KpiCard({ metric, card, tv }: { metric: MetricDef; card: PerformanceCard; tv: boolean }) {
  const change = card.change
  const trend = change === null ? null : change > 0 ? 'up' : change < 0 ? 'down' : 'flat'
  const TrendIcon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : trend === 'flat' ? Minus : ArrowRight
  return (
    <div className={cn('card flex flex-col justify-between border-t-4 border-t-brand-500', tv ? 'gap-2 px-6 py-4' : 'gap-3 p-5')}>
      <div className="flex items-start justify-between gap-2">
        <span className={cn('font-medium text-ink-secondary', tv ? 'text-xl' : 'text-sm')}>{metric.cardLabel}</span>
        <span className={cn('flex shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700', tv ? 'size-14' : 'size-10')}>
          <metric.icon className={tv ? 'size-8' : 'size-5'} aria-hidden />
        </span>
      </div>
      <div>
        <p className={cn('font-bold tabular-nums leading-none text-ink', tv ? 'text-6xl' : 'text-4xl sm:text-5xl')}>
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
          {change === null
            ? 'Нет данных для сравнения'
            : `Изменение за день: ${formatChange(change, metric.percent)}`}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Таблица по дням месяца
// ---------------------------------------------------------------------------

export function DailyTable({ data, tv, onEdit }: { data: MonthlyPerformance; tv: boolean; onEdit?: (day: PerformanceDay) => void }) {
  const cell = tv ? 'px-0 py-2.5 text-lg tracking-tight' : 'px-2 py-2.5 text-sm'
  return (
    <section className="card min-w-0 overflow-hidden" aria-label="Показатели по дням">
      <div className={cn(tv ? 'overflow-hidden' : 'overflow-x-auto')} tabIndex={tv ? undefined : 0}>
        <table className={cn('w-full border-collapse text-center tabular-nums', tv && 'table-fixed')}>
          <thead>
            <tr className="border-b border-border bg-surface-muted">
              <th scope="col" className={cn('sticky left-0 z-10 bg-surface-muted text-left font-semibold text-ink', tv ? 'w-[17.5rem] px-4 py-2.5 text-xl' : 'min-w-52 px-4 py-2.5 text-sm')}>
                {data.month_label}
              </th>
              {data.days.map((day) => {
                const weekend = day.weekday >= 6
                const editable = onEdit && !day.is_future
                return (
                  <th
                    key={day.date}
                    scope="col"
                    aria-current={day.is_today ? 'date' : undefined}
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
                <th scope="row" className={cn('sticky left-0 z-10 whitespace-nowrap bg-surface text-left font-medium text-ink', tv ? 'px-4 py-2.5 text-xl' : 'px-4 py-2.5 text-sm')}>
                  {metric.label}
                </th>
                {data.days.map((day) => {
                  const value = day[metric.key]
                  const manual = day.manual_fields.includes(metric.key)
                  const missing = !day.is_future && value === null
                  return (
                    <td
                      key={day.date}
                      data-missing={missing || undefined}
                      className={cn(
                        cell,
                        day.is_today && 'bg-brand-50 font-semibold',
                        missing && !day.is_today && 'bg-[repeating-linear-gradient(135deg,var(--color-surface-muted)_0_6px,var(--color-surface)_6px_12px)]',
                        value === null ? 'text-ink-muted' : 'text-ink',
                      )}
                      title={manual ? `Скорректировано вручную${day.manual_comment ? `: ${day.manual_comment}` : ''}` : missing ? 'Нет данных' : undefined}
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
          Зелёный — сегодня · «—» на штриховке — нет данных · * — скорректировано вручную
          {onEdit ? ' · нажмите на число дня, чтобы скорректировать' : ''}
        </p>
      ) : null}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Ручная корректировка (только сотрудники с правом — проверяет backend)
// ---------------------------------------------------------------------------

export function CorrectionModal({ day, onClose }: { day: PerformanceDay; onClose: () => void }) {
  const queryClient = useQueryClient()
  const initial = (key: PerformanceMetric) => (day[key] === null ? '' : String(day[key]))
  const [values, setValues] = useState<Record<PerformanceMetric, string>>(() => ({
    attendance_percent: initial('attendance_percent'),
    homework_percent: initial('homework_percent'),
    active_groups: initial('active_groups'),
    active_students: initial('active_students'),
  }))
  const [comment, setComment] = useState(day.manual_comment)

  const mutation = useMutation({
    mutationFn: (payload: CorrectionPayload) => monthlyPerformanceApi.correct(day.date, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['monthly-performance'] })
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
