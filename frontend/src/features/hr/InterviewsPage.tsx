import { useMemo, useState } from 'react'
import { addDays, addMonths, endOfMonth, format, parseISO, startOfMonth, startOfWeek } from 'date-fns'
import { ru } from 'date-fns/locale'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useAllVacancies, useInterviews, useRecruitmentMeta } from '@/hooks/useHr'
import { extractErrorMessage } from '@/lib/apiError'
import type { Interview, InterviewStatus } from '@/types/hr'
import { cn } from '@/utils/cn'

import { DAY_MINUTES, DAY_START, assignLanes, fromMinutes, hourMarks, place } from '../scheduleBoard/timeGrid'
import { InterviewForm, InterviewModal } from './InterviewDialogs'
import { minutesOfDay, officeDate, officeTime } from './shared'

type View = 'day' | 'week' | 'month'

const HOUR_PX = 48
const PX_PER_MIN = HOUR_PX / 60
const ISO = 'yyyy-MM-dd'

// Только токены темы (index.css): назначено — фирменный цвет, проведено — нейтрально-синий, отменено — серое зачёркнутое.
const EVENT_STYLE: Record<InterviewStatus, string> = {
  scheduled: 'border-brand-200 bg-brand-50 text-brand-700',
  completed: 'border-info/30 bg-info-soft text-info',
  cancelled: 'border-border bg-surface-muted text-ink-muted line-through',
}

function rangeOf(view: View, anchor: Date): { from: Date; to: Date; days: Date[] } {
  if (view === 'day') return { from: anchor, to: anchor, days: [anchor] }
  if (view === 'week') {
    const from = startOfWeek(anchor, { weekStartsOn: 1 })
    const days = Array.from({ length: 7 }, (_, i) => addDays(from, i))
    return { from, to: days[6], days }
  }
  const from = startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 })
  const last = startOfWeek(endOfMonth(anchor), { weekStartsOn: 1 })
  const days: Date[] = []
  for (let d = from; d <= addDays(last, 6); d = addDays(d, 1)) days.push(d)
  return { from, to: days[days.length - 1], days }
}

function shift(view: View, anchor: Date, step: number): Date {
  if (view === 'day') return addDays(anchor, step)
  if (view === 'week') return addDays(anchor, step * 7)
  return addMonths(anchor, step)
}

function titleOf(view: View, anchor: Date, days: Date[]): string {
  if (view === 'day') return format(anchor, 'EEEE, d MMMM yyyy', { locale: ru })
  if (view === 'week') return `${format(days[0], 'd MMM', { locale: ru })} – ${format(days[6], 'd MMM yyyy', { locale: ru })}`
  const label = format(anchor, 'LLLL yyyy', { locale: ru })
  return label.charAt(0).toUpperCase() + label.slice(1)
}

/** /hr/interviews — календарь собеседований: день, неделя, месяц. Фильтры по
 * интервьюеру, вакансии и статусу; событие открывает карточку встречи со
 * ссылкой на кандидата. */
export function HrInterviewsPage() {
  const meta = useRecruitmentMeta()
  const vacancies = useAllVacancies()
  const [view, setView] = useState<View>('week')
  const [anchor, setAnchor] = useState<Date | null>(null)
  const [filters, setFilters] = useState({ interviewer: '', vacancy: '', status: '' })
  const [opened, setOpened] = useState<Interview | null>(null)
  const [creatingAt, setCreatingAt] = useState<string | null>(null)

  const today = meta.data ? parseISO(meta.data.today) : null
  const current = anchor ?? today ?? new Date()
  const range = rangeOf(view, current)
  const interviews = useInterviews({
    date_from: format(range.from, ISO), date_to: format(range.to, ISO),
    interviewer: filters.interviewer || undefined, vacancy: filters.vacancy || undefined, status: filters.status || undefined,
  })
  const byDay = useMemo(() => {
    const map = new Map<string, Interview[]>()
    for (const item of interviews.data ?? []) {
      const key = officeDate(item.scheduled_at)
      map.set(key, [...(map.get(key) ?? []), item])
    }
    return map
  }, [interviews.data])
  // Карточка открытого события обновляется вместе со списком (после переноса и т. п.).
  const openedFresh = opened ? (interviews.data ?? []).find((i) => i.id === opened.id) ?? opened : null

  return (
    <div className="space-y-5">
      <PageHeader
        title="Собеседования"
        description="Календарь встреч с кандидатами"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreatingAt('')}>Назначить собеседование</Button>}
      />
      <Card>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" aria-label="Назад" onClick={() => setAnchor(shift(view, current, -1))}><ChevronLeft className="size-4" aria-hidden /></Button>
            <Button size="sm" variant="secondary" onClick={() => setAnchor(today)}>Сегодня</Button>
            <Button size="sm" variant="secondary" aria-label="Вперёд" onClick={() => setAnchor(shift(view, current, 1))}><ChevronRight className="size-4" aria-hidden /></Button>
            <h2 className="ml-1 text-base font-semibold text-ink first-letter:uppercase">{titleOf(view, current, range.days)}</h2>
          </div>
          <SegmentedControl
            aria-label="Вид календаря"
            value={view}
            onChange={setView}
            options={[{ value: 'day', label: 'День' }, { value: 'week', label: 'Неделя' }, { value: 'month', label: 'Месяц' }]}
          />
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <Select aria-label="Интервьюер" value={filters.interviewer} onChange={(e) => setFilters((f) => ({ ...f, interviewer: e.target.value }))} placeholder="Все интервьюеры"
            options={(meta.data?.people ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))} />
          <Select aria-label="Вакансия" value={filters.vacancy} onChange={(e) => setFilters((f) => ({ ...f, vacancy: e.target.value }))} placeholder="Все вакансии"
            options={(vacancies.data?.results ?? []).map((v) => ({ value: String(v.id), label: v.title }))} />
          <Select aria-label="Статус" value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} placeholder="Все статусы"
            options={meta.data?.interview_statuses ?? []} />
        </div>
      </Card>

      {interviews.isPending || !meta.data ? (
        <LoadingState label="Загружаем календарь…" />
      ) : interviews.isError ? (
        <ErrorState message={extractErrorMessage(interviews.error)} onRetry={() => void interviews.refetch()} />
      ) : view === 'month' ? (
        <MonthGrid days={range.days} month={current.getMonth()} today={meta.data.today} byDay={byDay} onOpen={setOpened}
          onDay={(day) => { setAnchor(day); setView('day') }} />
      ) : (
        <>
          <TimeColumns days={range.days} today={meta.data.today} byDay={byDay} onOpen={setOpened}
            onSlot={(value) => setCreatingAt(value)} />
          <AgendaList items={interviews.data} onOpen={setOpened} />
        </>
      )}

      <InterviewModal interview={openedFresh} onClose={() => setOpened(null)} />
      <Modal isOpen={creatingAt !== null} onClose={() => setCreatingAt(null)} title="Назначить собеседование">
        {creatingAt !== null && meta.data ? <InterviewForm meta={meta.data} defaultStart={creatingAt || undefined} onClose={() => setCreatingAt(null)} /> : null}
      </Modal>
    </div>
  )
}

/** День и неделя: шкала 08:00–24:00, встречи по реальному времени, пересекающиеся — рядом. */
function TimeColumns({ days, today, byDay, onOpen, onSlot }: {
  days: Date[]
  today: string
  byDay: Map<string, Interview[]>
  onOpen: (interview: Interview) => void
  onSlot: (value: string) => void
}) {
  const marks = hourMarks()
  const height = DAY_MINUTES * PX_PER_MIN
  return (
    <Card padding="none" className="hidden overflow-x-auto md:block">
      <div className="flex min-w-[720px]">
        <div className="w-14 shrink-0 border-r border-border pt-10">
          <div className="relative" style={{ height }}>
            {marks.map((mark, i) => (
              <span key={mark} className="absolute right-2 -translate-y-1/2 text-xs tabular-nums text-ink-muted" style={{ top: i * HOUR_PX }}>{mark}</span>
            ))}
          </div>
        </div>
        {days.map((day) => {
          const key = format(day, ISO)
          const items = assignLanes((byDay.get(key) ?? []).map((item) => {
            const start = minutesOfDay(item.scheduled_at)
            return { item, start: fromMinutes(start), end: fromMinutes(start + item.duration_minutes) }
          }))
          return (
            <div key={key} className="min-w-0 flex-1 border-r border-border last:border-r-0">
              <div className={cn('flex h-10 items-center justify-center border-b border-border text-sm font-medium', key === today ? 'text-brand-700' : 'text-ink')}>
                {format(day, 'EEEEEE, d MMM', { locale: ru })}
              </div>
              <div
                className="relative cursor-pointer"
                style={{ height, backgroundImage: `repeating-linear-gradient(to bottom, var(--color-border) 0 1px, transparent 1px ${HOUR_PX}px)` }}
                onClick={(e) => {
                  const offset = (e.clientY - e.currentTarget.getBoundingClientRect().top) / PX_PER_MIN
                  const minutes = DAY_START + Math.floor(offset / 30) * 30
                  onSlot(`${key}T${fromMinutes(minutes)}`)
                }}
                title="Нажмите на свободное время, чтобы назначить собеседование"
              >
                {items.map(({ item: { item, start, end }, lane, lanes }) => {
                  const box = place(start, end)
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onOpen(item) }}
                      className={cn('absolute overflow-hidden rounded-md border px-1.5 py-0.5 text-left text-xs', EVENT_STYLE[item.status])}
                      style={{ top: box.top * PX_PER_MIN, height: Math.max(box.height * PX_PER_MIN, 20), left: `${(lane / lanes) * 100}%`, width: `${100 / lanes}%` }}
                    >
                      <span className="block font-medium tabular-nums">{start}–{end}</span>
                      <span className="block truncate">{item.candidate_info.full_name}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

/** Список встреч периода: на телефоне — основной вид, на компьютере — под сеткой. */
function AgendaList({ items, onOpen }: { items: Interview[]; onOpen: (interview: Interview) => void }) {
  if (!items.length) {
    return <p className="rounded-xl bg-surface px-4 py-6 text-center text-sm text-ink-secondary">В этом периоде собеседований нет.</p>
  }
  return (
    <Card title="Список встреч" padding="none">
      <ul className="divide-y divide-border">
        {items.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
            <button type="button" className="min-w-0 text-left" onClick={() => onOpen(item)}>
              <span className="block text-sm font-medium tabular-nums text-ink">
                {format(parseISO(officeDate(item.scheduled_at)), 'd MMM, EEEEEE', { locale: ru })} · {officeTime(item.scheduled_at)}
              </span>
              <span className="block text-sm text-ink-secondary">{item.candidate_info.full_name} · {item.interviewer_info.full_name}</span>
            </button>
            <div className="flex items-center gap-2">
              <span className={cn('rounded-full border px-2 py-0.5 text-xs', EVENT_STYLE[item.status])}>{item.status_label}</span>
              <Link to={`/hr/candidates/${item.candidate}`} className="text-xs text-brand-700 hover:underline">Кандидат</Link>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function MonthGrid({ days, month, today, byDay, onOpen, onDay }: {
  days: Date[]
  month: number
  today: string
  byDay: Map<string, Interview[]>
  onOpen: (interview: Interview) => void
  onDay: (day: Date) => void
}) {
  const weekdays = days.slice(0, 7).map((d) => format(d, 'EEEEEE', { locale: ru }))
  return (
    <Card padding="none" className="overflow-x-auto">
      <div className="grid min-w-[640px] grid-cols-7">
        {weekdays.map((label) => <div key={label} className="border-b border-border px-2 py-2 text-xs font-medium uppercase text-ink-muted">{label}</div>)}
        {days.map((day) => {
          const key = format(day, ISO)
          const items = byDay.get(key) ?? []
          return (
            <div key={key} className={cn('min-h-24 border-b border-r border-border p-1.5', day.getMonth() !== month && 'bg-surface-muted')}>
              <button type="button" onClick={() => onDay(day)} className={cn('mb-1 text-xs font-medium hover:underline', key === today ? 'text-brand-700' : 'text-ink-secondary')}>
                {format(day, 'd')}
              </button>
              <div className="space-y-0.5">
                {items.slice(0, 3).map((item) => (
                  <button key={item.id} type="button" onClick={() => onOpen(item)} className={cn('block w-full truncate rounded border px-1 text-left text-xs', EVENT_STYLE[item.status])}>
                    {officeTime(item.scheduled_at)} {item.candidate_info.full_name}
                  </button>
                ))}
                {items.length > 3 ? (
                  <button type="button" onClick={() => onDay(day)} className="text-xs text-brand-700 hover:underline">ещё {items.length - 3}</button>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

