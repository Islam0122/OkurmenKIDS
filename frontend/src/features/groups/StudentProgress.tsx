import { Fragment, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, Minus, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useGroupStudentProgress, useStudentProgressDetail } from '@/hooks/useKPI'
import type { StudentProgressParams, StudentProgressRow } from '@/types/studentProgress'
import { cn } from '@/utils/cn'
import { formatDateShort, formatRuPercent } from '@/utils/format'

export const NO_DATA = 'Нет данных'

type SortKey = 'name' | 'attendance_rate' | 'homework_rate' | 'average_score'

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'name', label: 'По имени' },
  { value: 'attendance_rate', label: 'По посещаемости' },
  { value: 'homework_rate', label: 'По выполнению ДЗ' },
  { value: 'average_score', label: 'По среднему баллу' },
]

const ATTENDANCE_TONE: Record<string, BadgeTone> = { present: 'success', late: 'warning', absent: 'danger', excused: 'info' }
const HOMEWORK_TONE: Record<string, BadgeTone> = { checked: 'success', submitted: 'success', late: 'warning', not_submitted: 'danger' }

function decimal(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1).replace('.', ',')
}

export function percentText(value: number | null): string {
  return value === null ? NO_DATA : formatRuPercent(value)
}

export function scoreText(value: number | null): string {
  return value === null ? NO_DATA : `${decimal(value)}/10`
}

/** Sort `rows` by `key`; a student with no data always goes last, whatever the direction. */
export function sortRows(rows: StudentProgressRow[], key: SortKey, descending: boolean): StudentProgressRow[] {
  const byName = (a: StudentProgressRow, b: StudentProgressRow) => a.name.localeCompare(b.name, 'ru')
  if (key === 'name') return [...rows].sort((a, b) => (descending ? byName(b, a) : byName(a, b)))
  return [...rows].sort((a, b) => {
    const left = a[key]
    const right = b[key]
    if (left === null || right === null) return left === right ? byName(a, b) : left === null ? 1 : -1
    return (descending ? right - left : left - right) || byName(a, b)
  })
}

/** «+5 п.п.» / «−0,4» against the previous comparable period; nothing when there is no comparison. */
function Change({ value, unit }: { value: number | null; unit: 'pp' | 'score' }) {
  if (value === null) return null
  const suffix = unit === 'pp' ? ' п.п.' : ''
  if (value === 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-ink-muted" title="Без изменений к прошлому периоду">
        <Minus className="size-3" aria-hidden />0{suffix}
      </span>
    )
  }
  const up = value > 0
  return (
    <span
      className={cn('inline-flex items-center gap-0.5 text-xs font-medium', up ? 'text-brand-700' : 'text-danger')}
      title="Изменение к прошлому периоду"
    >
      {up ? <ArrowUp className="size-3" aria-hidden /> : <ArrowDown className="size-3" aria-hidden />}
      {up ? '+' : '−'}
      {decimal(Math.abs(value))}
      {suffix}
    </span>
  )
}

function Metric({ label, value, sub, change }: { label: string; value: string; sub?: string; change?: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-secondary">{label}</dt>
      <dd className={cn('mt-0.5 font-medium', value === NO_DATA ? 'text-ink-muted' : 'text-ink')}>
        {value} {change}
      </dd>
      {sub ? <dd className="text-xs text-ink-muted">{sub}</dd> : null}
    </div>
  )
}

/** A short sentence about the change against the previous period. */
export function dynamicsSummary(row: StudentProgressRow): string {
  const parts: string[] = []
  const describe = (label: string, value: number | null, unit: string) => {
    if (value === null) return
    if (value === 0) parts.push(`${label} без изменений`)
    else parts.push(`${label} ${value > 0 ? 'выросла' : 'снизилась'} на ${decimal(Math.abs(value))}${unit}`)
  }
  describe('посещаемость', row.change.attendance_rate, ' п.п.')
  describe('доля выполненных ДЗ', row.change.homework_rate, ' п.п.')
  if (row.change.average_score !== null) {
    const v = row.change.average_score
    parts.push(v === 0 ? 'средний балл без изменений' : `средний балл ${v > 0 ? 'вырос' : 'снизился'} на ${decimal(Math.abs(v))}`)
  }
  if (row.change.test_average !== null) {
    const v = row.change.test_average
    parts.push(v === 0 ? 'результат тестов без изменений' : `результат тестов ${v > 0 ? 'вырос' : 'снизился'} на ${decimal(Math.abs(v))} п.п.`)
  }
  if (!parts.length) return 'Недостаточно данных для сравнения с прошлым периодом.'
  const text = parts.join(', ')
  return `По сравнению с прошлым периодом ${text}.`
}

/**
 * «Прогресс студентов» — under the group KPI card, for the same period:
 * each student's attendance, homework, scores and tests, with search, sorting
 * and a row that opens the student's lessons of the period. A table on wide
 * screens, compact cards on a phone.
 */
export function StudentProgress({ groupId, params }: { groupId: number; params: StudentProgressParams }) {
  const { data, isPending, isError, refetch } = useGroupStudentProgress(groupId, params)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [descending, setDescending] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)

  const rows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('ru')
    const found = (data?.students ?? []).filter((row) => !needle || row.name.toLocaleLowerCase('ru').includes(needle))
    return sortRows(found, sortKey, descending)
  }, [data, search, sortKey, descending])

  const changeSort = (key: SortKey) => {
    setSortKey(key)
    // A metric reads best from the highest; a name from А to Я.
    setDescending(key !== 'name')
  }
  const toggle = (id: number) => setOpenId((current) => (current === id ? null : id))

  return (
    <section className="mt-6" aria-labelledby="student-progress-title">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 id="student-progress-title" className="section-title">Прогресс студентов</h3>
          {data ? (
            <p className="mt-0.5 text-xs text-ink-muted">
              Динамика — к периоду {formatDateShort(data.comparison.start_date)} — {formatDateShort(data.comparison.end_date)}
            </p>
          ) : null}
        </div>
      </div>

      {isPending ? <LoadingState label="Считаем прогресс студентов…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.students.length === 0 ? (
        <EmptyState icon={Users} title="В этот период в группе не было студентов" />
      ) : null}

      {data && data.students.length > 0 ? (
        <>
          <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_14rem_auto]">
            <SearchInput value={search} onChange={setSearch} placeholder="Поиск по имени студента" />
            <Select
              aria-label="Сортировка"
              value={sortKey}
              onChange={(event) => changeSort(event.target.value as SortKey)}
              options={SORT_OPTIONS}
            />
            <button
              type="button"
              onClick={() => setDescending((value) => !value)}
              className="form-control inline-flex items-center justify-center gap-1.5 whitespace-nowrap"
              aria-label={descending ? 'По убыванию' : 'По возрастанию'}
            >
              {descending ? <ArrowDown className="size-4" aria-hidden /> : <ArrowUp className="size-4" aria-hidden />}
              {descending ? 'По убыванию' : 'По возрастанию'}
            </button>
          </div>

          {rows.length === 0 ? (
            <EmptyState title="Никого не нашли" description="Проверьте имя в поиске." />
          ) : (
            <>
              {/* Tablets and computers: a table, a row opens its details below it. */}
              <div className="card hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-ink-secondary">
                      <th className="px-4 py-2.5 font-medium">Студент</th>
                      <th className="px-3 py-2.5 text-right font-medium">Занятия</th>
                      <th className="px-3 py-2.5 text-right font-medium">Посещаемость</th>
                      <th className="px-3 py-2.5 text-right font-medium">Пропуски</th>
                      <th className="px-3 py-2.5 text-right font-medium">ДЗ</th>
                      <th className="px-3 py-2.5 text-right font-medium">Средний балл</th>
                      <th className="px-3 py-2.5 text-right font-medium">Тесты</th>
                      <th className="w-10 px-2 py-2.5"><span className="sr-only">Подробнее</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const isOpen = openId === row.id
                      return (
                        <Fragment key={row.id}>
                          <tr
                            className={cn('cursor-pointer border-b border-border last:border-0 hover:bg-surface-hover', isOpen && 'bg-brand-50/40')}
                            onClick={() => toggle(row.id)}
                            data-testid={`progress-row-${row.id}`}
                          >
                            <td className="px-4 py-3">
                              <p className="font-medium text-ink">{row.name}</p>
                              {!row.in_group_now ? <p className="text-xs text-ink-muted">Сейчас не в этой группе</p> : null}
                            </td>
                            <td className="px-3 py-3 text-right tabular-nums">
                              {row.attended} / {row.lessons_held}
                            </td>
                            <td className="px-3 py-3 text-right tabular-nums">
                              <span className={row.attendance_rate === null ? 'text-ink-muted' : ''}>{percentText(row.attendance_rate)}</span>
                              <div><Change value={row.change.attendance_rate} unit="pp" /></div>
                            </td>
                            <td className="px-3 py-3 text-right tabular-nums">{row.absences}</td>
                            <td className="px-3 py-3 text-right tabular-nums">
                              <span className={row.homework_rate === null ? 'text-ink-muted' : ''}>{percentText(row.homework_rate)}</span>
                              {row.homework_due ? <div className="text-xs text-ink-muted">{row.homework_done} из {row.homework_due}</div> : null}
                              <div><Change value={row.change.homework_rate} unit="pp" /></div>
                            </td>
                            <td className="px-3 py-3 text-right tabular-nums">
                              <span className={row.average_score === null ? 'text-ink-muted' : ''}>{scoreText(row.average_score)}</span>
                              <div><Change value={row.change.average_score} unit="score" /></div>
                            </td>
                            <td className="px-3 py-3 text-right tabular-nums">
                              <span className={row.test_average === null ? 'text-ink-muted' : ''}>{percentText(row.test_average)}</span>
                              {row.tests_count ? <div className="text-xs text-ink-muted">{row.tests_count} шт.</div> : null}
                            </td>
                            <td className="px-2 py-3">
                              <button
                                type="button"
                                aria-expanded={isOpen}
                                aria-label={`${isOpen ? 'Скрыть' : 'Показать'} подробности: ${row.name}`}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  toggle(row.id)
                                }}
                                className="flex size-7 items-center justify-center rounded-md text-ink-muted hover:bg-surface-hover"
                              >
                                <ChevronDown className={cn('size-4 transition-transform', isOpen && 'rotate-180')} aria-hidden />
                              </button>
                            </td>
                          </tr>
                          {isOpen ? (
                            <tr className="border-b border-border bg-surface-muted/50">
                              <td colSpan={8} className="px-4 py-4">
                                <StudentProgressDetailPanel groupId={groupId} row={row} params={params} />
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Phones: compact cards. */}
              <ul className="space-y-3 md:hidden">
                {rows.map((row) => {
                  const isOpen = openId === row.id
                  return (
                    <li key={row.id} className="card card-body" data-testid={`progress-card-${row.id}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-medium text-ink">{row.name}</p>
                          <p className="text-xs text-ink-muted">
                            Занятий: {row.attended} из {row.lessons_held} · пропусков: {row.absences}
                          </p>
                        </div>
                        <button
                          type="button"
                          aria-expanded={isOpen}
                          aria-label={`${isOpen ? 'Скрыть' : 'Показать'} подробности: ${row.name}`}
                          onClick={() => toggle(row.id)}
                          className="flex size-8 shrink-0 items-center justify-center rounded-md text-ink-muted hover:bg-surface-hover"
                        >
                          <ChevronDown className={cn('size-4 transition-transform', isOpen && 'rotate-180')} aria-hidden />
                        </button>
                      </div>
                      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm min-[420px]:grid-cols-4">
                        <Metric label="Посещаемость" value={percentText(row.attendance_rate)} change={<Change value={row.change.attendance_rate} unit="pp" />} />
                        <Metric
                          label="ДЗ"
                          value={percentText(row.homework_rate)}
                          sub={row.homework_due ? `${row.homework_done} из ${row.homework_due}` : undefined}
                          change={<Change value={row.change.homework_rate} unit="pp" />}
                        />
                        <Metric label="Средний балл" value={scoreText(row.average_score)} change={<Change value={row.change.average_score} unit="score" />} />
                        <Metric label="Тесты" value={percentText(row.test_average)} />
                      </dl>
                      {isOpen ? (
                        <div className="mt-4 border-t border-border pt-4">
                          <StudentProgressDetailPanel groupId={groupId} row={row} params={params} />
                        </div>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </>
      ) : null}
    </section>
  )
}

/** The opened row: the student's lessons of the period with attendance and
 * homework, their tests, a short summary of the dynamics and a link to the
 * existing student card. */
function StudentProgressDetailPanel({ groupId, row, params }: { groupId: number; row: StudentProgressRow; params: StudentProgressParams }) {
  const { data, isPending, isError, refetch } = useStudentProgressDetail(groupId, row.id, params)

  return (
    <div className="space-y-4" data-testid={`progress-detail-${row.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm text-ink-secondary">{dynamicsSummary(row)}</p>
        <Link to={`/app/students/${row.id}`} className="text-sm font-medium text-brand-700 hover:underline">
          Карточка студента
        </Link>
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data ? (
        <>
          {data.lessons.length === 0 ? (
            <p className="text-sm text-ink-muted">За этот период проведённых занятий нет.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
              {data.lessons.map((lesson) => (
                <li key={lesson.id} className="grid grid-cols-1 gap-2 px-3 py-2.5 text-sm sm:grid-cols-[7rem_minmax(0,1fr)_auto] sm:items-start">
                  <div className="text-ink-secondary tabular-nums">
                    {formatDateShort(lesson.date)}
                    <span className="block text-xs text-ink-muted">Занятие {lesson.lesson_number}</span>
                  </div>
                  <div className="min-w-0">
                    <Link to={`/app/lessons/${lesson.id}`} className="text-ink hover:text-brand-700 hover:underline">
                      {lesson.topic || lesson.subject || `Занятие ${lesson.lesson_number}`}
                    </Link>
                    {lesson.homework.length ? (
                      <ul className="mt-1 space-y-1">
                        {lesson.homework.map((homework) => (
                          <li key={homework.id} className="flex flex-wrap items-center gap-1.5 text-xs">
                            <span className="text-ink-secondary">ДЗ: {homework.title}</span>
                            <Badge tone={homework.status ? HOMEWORK_TONE[homework.status] ?? 'muted' : 'muted'}>{homework.status_display}</Badge>
                            {homework.score !== null ? <span className="font-medium text-ink">{homework.score}/10</span> : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-xs text-ink-muted">ДЗ не задавалось</p>
                    )}
                  </div>
                  <div className="sm:text-right">
                    {lesson.attendance ? (
                      <Badge tone={ATTENDANCE_TONE[lesson.attendance] ?? 'muted'}>{lesson.attendance_display}</Badge>
                    ) : (
                      <Badge tone="muted">Не отмечено</Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {data.tests.length ? (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-secondary">Тесты</p>
              <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
                {data.tests.map((test) => (
                  <li key={test.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                    <span className="min-w-0 text-ink">
                      {test.title}
                      {test.date ? <span className="ml-2 text-xs text-ink-muted">{formatDateShort(test.date)}</span> : null}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="font-medium tabular-nums">{formatRuPercent(test.score)}</span>
                      {test.passed !== null ? <Badge tone={test.passed ? 'success' : 'danger'}>{test.passed ? 'Сдан' : 'Не сдан'}</Badge> : null}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
