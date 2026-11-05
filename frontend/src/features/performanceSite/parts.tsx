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
  type CardMetric,
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

export const NO_DATA = 'Нет данных'
export const NO_LESSONS = 'Нет занятий'

export interface RowDef {
  key: PerformanceMetric
  label: string
  percent: boolean
}

/** Строки таблицы — плановые и фактические показатели не смешиваются. */
export const ROWS: RowDef[] = [
  { key: 'scheduled_groups', label: 'Групп по расписанию', percent: false },
  { key: 'held_groups', label: 'Проведено занятий в группах', percent: false },
  { key: 'scheduled_students', label: 'Студентов по расписанию', percent: false },
  { key: 'attended_students', label: 'Посетили занятия', percent: false },
  { key: 'attendance_percent', label: 'Посещаемость', percent: true },
  { key: 'homework_percent', label: 'Домашние задания', percent: true },
]

export interface CardDef {
  key: CardMetric
  label: string
  icon: LucideIcon
  percent: boolean
}

export const CARDS: CardDef[] = [
  { key: 'attendance_percent', label: 'Посещаемость', icon: CalendarCheck, percent: true },
  { key: 'homework_percent', label: 'Выполнение домашних заданий', icon: NotebookPen, percent: true },
  { key: 'scheduled_groups', label: 'Групп по расписанию', icon: Users, percent: false },
  { key: 'scheduled_students', label: 'Студентов по расписанию', icon: GraduationCap, percent: false },
]

export function formatValue(value: number | null | undefined, percent: boolean): string {
  return percent ? formatPct(value) : formatCount(value)
}

/** Текст ячейки: будущий день — пусто; нет данных — «Нет данных»; день без
 * занятий — 0 для групп и студентов, «Нет занятий» для посещаемости. */
export function cellText(day: PerformanceDay, row: RowDef, short: boolean): string {
  if (day.is_future) return ''
  const value = day[row.key]
  if (value === null || !day.has_data) {
    if (short) return '—'
    return day.no_lessons && row.key === 'attendance_percent' ? NO_LESSONS : NO_DATA
  }
  if (row.percent) return short ? String(Math.round(value)) : `${Math.round(value)}%`
  return formatCount(value)
}

// ---------------------------------------------------------------------------
// Карточка показателя
// ---------------------------------------------------------------------------

function cardNote(card: CardDef, data: PerformanceCard): string {
  if (!data.date) return ''
  const parts = [dayMonthLabel(data.date)]
  if (card.percent && data.month_average !== undefined && data.month_average !== null) {
    parts.push(`за месяц ${formatPct(data.month_average)}`)
  }
  if (card.key === 'scheduled_groups' && data.value !== null && data.held_groups !== undefined && data.held_groups !== null) {
    parts.push(`проведено ${formatCount(data.held_groups)} из ${formatCount(data.value)}`)
  }
  if (card.key === 'scheduled_students' && data.attended_students !== undefined && data.attended_students !== null) {
    parts.push(`посетили ${formatCount(data.attended_students)}`)
  }
  return parts.join(' · ')
}

export function KpiCard({ card, data, tv }: { card: CardDef; data: PerformanceCard; tv: boolean }) {
  const change = data.change
  const trend = change === null ? null : change > 0 ? 'up' : change < 0 ? 'down' : 'flat'
  const TrendIcon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : trend === 'flat' ? Minus : ArrowRight
  return (
    <div className={cn('card flex flex-col justify-between border-t-4 border-t-brand-500', tv ? 'gap-1.5 px-5 py-3' : 'gap-3 p-5')}>
      <div className="flex items-start justify-between gap-2">
        <span className={cn('font-medium text-ink-secondary', tv ? 'text-xl' : 'text-sm')}>{card.label}</span>
        <span className={cn('flex shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700', tv ? 'size-12' : 'size-10')}>
          <card.icon className={tv ? 'size-7' : 'size-5'} aria-hidden />
        </span>
      </div>
      <div>
        <p className={cn('font-bold tabular-nums leading-none text-ink', tv ? 'text-5xl' : 'text-4xl sm:text-5xl')}>
          {data.value === null ? <span className={cn('text-ink-muted', tv ? 'text-4xl' : 'text-2xl')}>{NO_DATA}</span> : formatValue(data.value, card.percent)}
        </p>
        <p className={cn('mt-2 text-ink-muted', tv ? 'text-xl' : 'text-xs')}>{cardNote(card, data)}</p>
      </div>
      <div
        className={cn(
          'flex items-center gap-1.5 font-medium',
          tv ? 'text-xl' : 'text-sm',
          trend === 'up' ? 'text-brand-700' : trend === 'down' ? 'text-danger' : 'text-ink-muted',
        )}
      >
        <TrendIcon className={tv ? 'size-7' : 'size-4'} aria-hidden />
        <span>
          {change === null
            ? 'Нет данных для сравнения'
            : card.percent || !data.previous_date
              ? `Изменение за день: ${formatChange(change, card.percent)}`
              : `Изменение к ${dayMonthLabel(data.previous_date)}: ${formatChange(change, card.percent)}`}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Таблица по дням месяца
// ---------------------------------------------------------------------------

export function DailyTable({ data, tv, onEdit }: { data: MonthlyPerformance; tv: boolean; onEdit?: (day: PerformanceDay) => void }) {
  const cell = tv ? 'px-0 py-1.5 text-lg tracking-tight' : 'px-1.5 py-2.5 text-sm'
  return (
    <section className="card min-w-0 overflow-hidden" aria-label="Показатели по дням">
      <div className={cn(tv ? 'overflow-hidden' : 'overflow-x-auto')} tabIndex={tv ? undefined : 0}>
        <table className={cn('w-full border-collapse text-center tabular-nums', tv && 'table-fixed')}>
          <thead>
            <tr className="border-b border-border bg-surface-muted">
              <th scope="col" className={cn('sticky left-0 z-10 bg-surface-muted text-left font-semibold text-ink', tv ? 'w-[19rem] px-4 py-1.5 text-xl' : 'min-w-60 px-4 py-2.5 text-sm')}>
                {data.month_label} {data.year}
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
                      !tv && 'min-w-[4.5rem]',
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
            {ROWS.map((row, index) => (
              <tr key={row.key} className={cn('border-b border-border last:border-0', index === 4 && 'border-t-2 border-t-border-strong')}>
                <th scope="row" className={cn('sticky left-0 z-10 whitespace-nowrap bg-surface text-left font-medium text-ink', tv ? 'px-4 py-1.5 text-xl' : 'px-4 py-2.5 text-sm')}>
                  {row.label}{tv && row.percent ? ', %' : ''}
                </th>
                {data.days.map((day) => {
                  const value = day[row.key]
                  const manual = day.manual_fields.includes(row.key)
                  const missing = !day.is_future && (value === null || !day.has_data)
                  const text = cellText(day, row, tv)
                  return (
                    <td
                      key={day.date}
                      data-missing={missing || undefined}
                      className={cn(
                        cell,
                        day.is_today && 'bg-brand-50 font-semibold',
                        missing && !day.is_today && 'bg-[repeating-linear-gradient(135deg,var(--color-surface-muted)_0_6px,var(--color-surface)_6px_12px)]',
                        missing ? 'text-ink-muted' : 'text-ink',
                        missing && !tv && 'text-[0.7rem] leading-tight',
                      )}
                      title={manual ? `Скорректировано вручную${day.manual_comment ? `: ${day.manual_comment}` : ''}` : missing ? cellText(day, row, false) : undefined}
                    >
                      {text}
                      {manual ? <sup className="text-brand-700">*</sup> : null}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={cn('border-t border-border px-4 text-ink-muted', tv ? 'py-1 text-base' : 'py-2 text-xs')}>
        {tv
          ? 'Зелёный — сегодня · «—» — нет занятий или нет данных · показатели по расписанию каждого дня'
          : <>
              Группы и студенты — по расписанию именно этого дня (у групп разные дни занятий) и составу групп на эту дату.
              {' '}Зелёный — сегодня · штриховка — нет данных · * — скорректировано вручную
              {onEdit ? ' · нажмите на число дня, чтобы скорректировать' : ''}
            </>}
      </p>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Ручная корректировка (только сотрудники с правом — проверяет backend)
// ---------------------------------------------------------------------------

export function CorrectionModal({ day, onClose }: { day: PerformanceDay; onClose: () => void }) {
  const queryClient = useQueryClient()
  const initial = (key: PerformanceMetric) => (day[key] === null ? '' : String(day[key]))
  const [values, setValues] = useState<Record<PerformanceMetric, string>>(
    () => Object.fromEntries(ROWS.map((row) => [row.key, initial(row.key)])) as Record<PerformanceMetric, string>,
  )
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
    for (const row of ROWS) {
      const raw = values[row.key].trim().replace(',', '.')
      if (raw === initial(row.key)) continue
      payload[row.key] = raw === '' ? null : Number(raw)
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
        {ROWS.map((row) => (
          <label key={row.key} className="flex flex-col gap-1 text-sm font-medium text-ink">
            {row.label}
            {row.percent ? ', %' : ''}
            <Input
              inputMode="decimal"
              value={values[row.key]}
              placeholder={NO_DATA}
              onChange={(event) => setValues((prev) => ({ ...prev, [row.key]: event.target.value }))}
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
