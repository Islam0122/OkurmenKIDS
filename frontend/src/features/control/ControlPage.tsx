import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  BookOpen,
  CalendarCheck,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Star,
} from 'lucide-react'

import type { ControlParams } from '@/api/control'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useAuth } from '@/hooks/useAuth'
import { useControlOverview } from '@/hooks/useControl'
import type { ControlPeriodKey, ControlRow, ControlStatus } from '@/types/control'
import { formatDateShort, formatRuPercent } from '@/utils/format'

import { ComponentCell, CONTROL_STATUS_TONE } from './controlDisplay'
import { ControlRowDrawer } from './ControlRowDrawer'

interface Draft {
  period: ControlPeriodKey
  startDate: string
  endDate: string
  teacher: string
  group: string
  subject: string
  status: string
}

const DEFAULT_DRAFT: Draft = {
  period: 'this_month',
  startDate: '',
  endDate: '',
  teacher: '',
  group: '',
  subject: '',
  status: '',
}

// Shown only until the backend's own (concretely labelled) options arrive.
const FALLBACK_PERIODS: { key: ControlPeriodKey; label: string }[] = [
  { key: 'today', label: 'Сегодня' },
  { key: 'this_week', label: 'Эта неделя' },
  { key: 'this_month', label: 'Этот месяц' },
  { key: 'last_month', label: 'Прошлый месяц' },
  { key: 'custom', label: 'Произвольный период' },
]

type SortKey = 'problems' | 'teacher' | 'group'

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'problems', label: 'Сначала проблемы' },
  { value: 'teacher', label: 'По тренеру' },
  { value: 'group', label: 'По группе' },
]

function toParams(draft: Draft): ControlParams {
  const custom = draft.period === 'custom' && draft.startDate && draft.endDate
  return {
    period: draft.period === 'custom' && !custom ? 'this_month' : draft.period,
    ...(custom ? { start_date: draft.startDate, end_date: draft.endDate } : {}),
    ...(draft.teacher ? { teacher: Number(draft.teacher) } : {}),
    ...(draft.group ? { group: Number(draft.group) } : {}),
    ...(draft.subject ? { subject: Number(draft.subject) } : {}),
    ...(draft.status ? { status: draft.status as ControlStatus } : {}),
  }
}

function teacherName(row: ControlRow): string {
  return row.teacher?.name ?? 'Тренер не назначен'
}

function sortRows(rows: ControlRow[], sort: SortKey): ControlRow[] {
  // "problems" keeps the backend's own priority order untouched.
  if (sort === 'problems') return rows
  const pick = sort === 'teacher' ? teacherName : (row: ControlRow) => row.group.name
  return [...rows].sort((a, b) => pick(a).localeCompare(pick(b), 'ru'))
}

export function ControlPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [draft, setDraft] = useState<Draft>(DEFAULT_DRAFT)
  const [applied, setApplied] = useState<ControlParams>(() => toParams(DEFAULT_DRAFT))
  const [sort, setSort] = useState<SortKey>('problems')
  const [selected, setSelected] = useState<ControlRow | null>(null)

  const { data, isPending, isError, refetch, isFetching } = useControlOverview(applied)
  const rows = useMemo(() => sortRows(data?.items ?? [], sort), [data, sort])
  const options = data?.options
  const periods = options?.periods ?? FALLBACK_PERIODS
  const summary = data?.summary
  const periodLabel = data
    ? `${data.filters.period_label} (${formatDateShort(data.filters.start_date)} – ${formatDateShort(data.filters.end_date)})`
    : ''

  const update = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }))
  const apply = () => setApplied(toParams(draft))
  const reset = () => {
    setDraft(DEFAULT_DRAFT)
    setApplied(toParams(DEFAULT_DRAFT))
    setSort('problems')
  }

  // The drawer re-reads the same period/subject scope the row was built from.
  const detailParams = {
    period: applied.period,
    start_date: applied.start_date,
    end_date: applied.end_date,
    subject: applied.subject,
  }

  return (
    <div>
      <PageHeader
        title="Контроль"
        description={
          isAdmin
            ? 'Контроль заполнения уроков и работы тренеров'
            : 'Контроль заполнения ваших уроков: посещаемость, домашние задания и баллы'
        }
      />

      <form
        className="mb-5 rounded-xl border border-border bg-surface p-4"
        onSubmit={(event) => {
          event.preventDefault()
          apply()
        }}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-xs font-medium text-ink-secondary">
            Период
            <Select
              className="mt-1"
              value={draft.period}
              onChange={(event) => update({ period: event.target.value as ControlPeriodKey })}
              options={periods.map((period) => ({ value: period.key, label: period.label }))}
            />
          </label>
          {isAdmin ? (
            <label className="text-xs font-medium text-ink-secondary">
              Тренер
              <Select
                className="mt-1"
                placeholder="Все тренеры"
                value={draft.teacher}
                onChange={(event) => update({ teacher: event.target.value })}
                options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))}
              />
            </label>
          ) : null}
          <label className="text-xs font-medium text-ink-secondary">
            Группа
            <Select
              className="mt-1"
              placeholder="Все группы"
              value={draft.group}
              onChange={(event) => update({ group: event.target.value })}
              options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
            />
          </label>
          <label className="text-xs font-medium text-ink-secondary">
            Предмет
            <Select
              className="mt-1"
              placeholder="Все предметы"
              value={draft.subject}
              onChange={(event) => update({ subject: event.target.value })}
              options={(options?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
            />
          </label>
          <label className="text-xs font-medium text-ink-secondary">
            Статус
            <Select
              className="mt-1"
              placeholder="Все"
              value={draft.status}
              onChange={(event) => update({ status: event.target.value })}
              options={(options?.statuses ?? []).map((s) => ({ value: s.key, label: s.label }))}
            />
          </label>
        </div>

        {draft.period === 'custom' ? (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:max-w-md">
            <label className="text-xs font-medium text-ink-secondary">
              С
              <DatePicker className="mt-1" value={draft.startDate} onChange={(e) => update({ startDate: e.target.value })} />
            </label>
            <label className="text-xs font-medium text-ink-secondary">
              По
              <DatePicker className="mt-1" value={draft.endDate} onChange={(e) => update({ endDate: e.target.value })} />
            </label>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button type="submit" size="sm" isLoading={isFetching && !isPending}>
            Применить
          </Button>
          <Button type="button" size="sm" variant="secondary" onClick={reset}>
            Сбросить
          </Button>
          {periodLabel ? <span className="text-xs text-ink-muted">{periodLabel}</span> : null}
        </div>
      </form>

      {isPending ? <LoadingState label="Проверяем заполнение занятий…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {summary ? (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-7">
          <StatCard
            icon={BookOpen}
            label="Занятий"
            value={summary.total_lessons}
            hint={summary.upcoming_lessons > 0 ? `+${summary.upcoming_lessons} предстоящих` : undefined}
          />
          <StatCard icon={CheckCircle2} label="Закрыто" value={summary.completed_lessons} />
          <StatCard
            icon={Clock3}
            label="Не закрыто"
            value={summary.not_closed_lessons}
            tone={summary.not_closed_lessons > 0 ? 'warning' : 'default'}
          />
          <StatCard icon={CalendarCheck} label="Посещаемость" value={formatRuPercent(summary.attendance_completion)} hint="отмечена" />
          <StatCard icon={Star} label="Оценки заполнены" value={formatRuPercent(summary.grade_completion)} />
          <StatCard icon={ClipboardCheck} label="ДЗ проверено" value={formatRuPercent(summary.homework_completion)} />
          <StatCard
            icon={AlertTriangle}
            label="Требуют внимания"
            value={summary.attention_count}
            tone={summary.attention_count > 0 ? 'danger' : 'default'}
          />
        </div>
      ) : null}

      {data ? (
        rows.length === 0 ? (
          applied.status && summary && summary.rows_total > 0 ? (
            <EmptyState title="Ничего не найдено" description="Нет строк с выбранным статусом за этот период." />
          ) : (
            <EmptyState
              title="Нет занятий"
              description="За выбранный период и фильтры занятий нет — проверять нечего."
            />
          )
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-sm text-ink-secondary">
                Строк: {rows.length}
                {applied.status ? ` из ${summary?.rows_total ?? rows.length}` : ''}
              </p>
              <div className="w-48">
                <Select
                  aria-label="Сортировка"
                  value={sort}
                  onChange={(event) => setSort(event.target.value as SortKey)}
                  options={SORT_OPTIONS}
                />
              </div>
            </div>

            {/* Desktop: one table. */}
            <div className="hidden overflow-x-auto rounded-xl border border-border bg-surface md:block">
              <table className="w-full divide-y divide-border text-sm">
                <thead className="bg-surface-muted">
                  <tr className="text-left text-ink-secondary">
                    <th scope="col" className="px-4 py-3 font-medium">Тренер</th>
                    <th scope="col" className="px-4 py-3 font-medium">Группа</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Уроков</th>
                    <th scope="col" className="px-4 py-3 font-medium">Посещаемость</th>
                    <th scope="col" className="px-4 py-3 font-medium">ДЗ</th>
                    <th scope="col" className="px-4 py-3 font-medium">Баллы</th>
                    <th scope="col" className="px-4 py-3 font-medium">Статус</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((row) => (
                    <tr
                      key={row.key}
                      tabIndex={0}
                      onClick={() => setSelected(row)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') setSelected(row)
                      }}
                      className="cursor-pointer hover:bg-surface-hover focus-visible:bg-surface-hover"
                    >
                      <td className="px-4 py-3 font-medium text-ink">{teacherName(row)}</td>
                      <td className="px-4 py-3 text-ink">
                        {row.group.name}
                        {row.subjects.length > 0 ? (
                          <span className="block text-xs text-ink-muted">{row.subjects.map((s) => s.name).join(', ')}</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-ink">
                        {row.lessons.total}
                        {row.lessons.upcoming > 0 ? (
                          <span className="block text-xs text-ink-muted">+{row.lessons.upcoming} предст.</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3"><ComponentCell component={row.attendance} /></td>
                      <td className="px-4 py-3"><ComponentCell component={row.homework} /></td>
                      <td className="px-4 py-3"><ComponentCell component={row.grades} /></td>
                      <td className="px-4 py-3">
                        <Badge tone={CONTROL_STATUS_TONE[row.status]}>{row.status_label}</Badge>
                        {row.lessons.not_closed > 0 ? (
                          <span className="mt-1 block text-xs text-ink-muted">не закрыто: {row.lessons.not_closed}</span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile: cards instead of a wide table. */}
            <ul className="space-y-3 md:hidden">
              {rows.map((row) => (
                <li key={row.key}>
                  <button
                    type="button"
                    onClick={() => setSelected(row)}
                    className="w-full rounded-xl border border-border bg-surface p-4 text-left"
                  >
                    <p className="font-semibold text-ink">{teacherName(row)}</p>
                    <p className="text-sm text-ink-secondary">{row.group.name}</p>
                    <dl className="mt-3 space-y-1.5 text-sm">
                      {(
                        [
                          ['Уроки закрыты', row.lessons],
                          ['Посещаемость', row.attendance],
                          ['ДЗ', row.homework],
                          ['Баллы', row.grades],
                        ] as const
                      ).map(([label, component]) => (
                        <div key={label} className="flex items-center justify-between">
                          <dt className="text-ink-secondary">{label}</dt>
                          <dd><ComponentCell component={component} /></dd>
                        </div>
                      ))}
                    </dl>
                    <div className="mt-3 flex items-center justify-between">
                      <Badge tone={CONTROL_STATUS_TONE[row.status]}>{row.status_label}</Badge>
                      <span className="inline-flex items-center gap-0.5 text-sm font-medium text-brand-700">
                        Подробнее <ChevronRight className="size-4" aria-hidden />
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )
      ) : null}

      <ControlRowDrawer
        key={selected?.key ?? 'none'}
        row={selected}
        params={detailParams}
        periodLabel={periodLabel}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}
