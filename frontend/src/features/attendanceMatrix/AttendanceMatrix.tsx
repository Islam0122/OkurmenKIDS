import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, BookX, Lock, CalendarDays, Check, ChevronLeft, ChevronRight, Download, Trophy, X } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { attendanceMatrixApi } from '@/api/attendanceMatrix'
import { useGroupMatrix } from '@/hooks/useAttendanceMatrix'
import { extractErrorMessage, isNotFound } from '@/lib/apiError'
import type { GroupMatrix, MatrixColumn, MatrixParams, MatrixPeriod, MatrixRow } from '@/types/attendanceMatrix'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/format'

import { CellModal } from './CellModal'
import type { CellTarget } from './CellModal'
import { CELL_STYLE, CellIcon, HOMEWORK_LABEL, LEVEL_STYLE, Legend, SummaryCard, WarningDot, pct, percentTone, shortDate, todayIso } from './ui'

const PERIOD_OPTIONS: { value: MatrixPeriod; label: string }[] = [
  { value: 'day', label: 'День' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'all', label: 'Всё время' },
]

const STATUS_FILTER = [
  { value: 'done', label: CELL_STYLE.done.label },
  { value: 'partial', label: CELL_STYLE.partial.label },
  { value: 'excused', label: CELL_STYLE.excused.label },
  { value: 'absent', label: CELL_STYLE.absent.label },
  { value: 'empty', label: CELL_STYLE.empty.label },
]
const HOMEWORK_FILTER = [
  { value: 'missed', label: 'Есть несданные ДЗ' },
  { value: 'done', label: 'Есть сданные ДЗ' },
]
const LEVEL_FILTER = [
  { value: 'warning', label: 'Все предупреждения' },
  { value: 'attention', label: 'Внимание и критично' },
  { value: 'critical', label: 'Только критично' },
]

/**
 * The monthly attendance & homework table of one group — the same component
 * for every role; the server decides what each may see and change
 * (backend: apps.attendance_matrix.access).
 */
export interface ExtraView {
  value: string
  label: string
  render: () => ReactNode
}

export interface AttendanceMatrixProps {
  groupId: number
  /** Controlled month/date (a page-level month picker); otherwise the table keeps its own. */
  date?: string
  onDateChange?: (date: string) => void
  /** Controlled subject ('' — all, an id, or 'none'); otherwise the subject buttons keep their own. */
  subject?: string
  onSubjectChange?: (subject: string) => void
  /** Only this trainer's lessons (a page-level trainer filter). */
  teacher?: number
  /** Extra views next to «Таблица за период» / «По занятиям», e.g. the trainer's «Журнал отметок». */
  extraViews?: ExtraView[]
}

type View = 'matrix' | 'lessons' | (string & {})

export function AttendanceMatrix({ groupId, date: dateProp, onDateChange, subject: subjectProp, onSubjectChange, teacher, extraViews = [] }: AttendanceMatrixProps) {
  const [view, setView] = useState<View>('matrix')
  const [period, setPeriod] = useState<MatrixPeriod>('month')
  const [ownDate, setOwnDate] = useState(dateProp ?? todayIso())
  const date = dateProp ?? ownDate
  const setDate = (value: string) => (onDateChange ? onDateChange(value) : setOwnDate(value))
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [homework, setHomework] = useState('')
  const [level, setLevel] = useState('')
  const [ownSubject, setOwnSubject] = useState('')
  const subject = subjectProp ?? ownSubject
  const setSubject = (value: string) => (onSubjectChange ? onSubjectChange(value) : setOwnSubject(value))
  const [lessonOpen, setLessonOpen] = useState<number | null>(null)
  const [target, setTarget] = useState<CellTarget | null>(null)
  const [exporting, setExporting] = useState(false)
  const { showToast } = useToast()

  const params: MatrixParams = {
    period,
    date,
    status: status as MatrixParams['status'],
    homework: homework as MatrixParams['homework'],
    level: level as MatrixParams['level'],
    subject: subject === '' ? undefined : subject === 'none' ? 'none' : Number(subject),
    teacher,
  }
  const { data, isPending, isError, error, refetch, isFetching } = useGroupMatrix(groupId, params)

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    return data ? (q ? data.rows.filter((r) => r.student.name.toLowerCase().includes(q)) : data.rows) : []
  }, [data, search])

  const onExport = async () => {
    setExporting(true)
    try {
      await attendanceMatrixApi.exportGroup(groupId, { ...params, search })
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сформировать Excel'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const viewSwitch = (
    <SegmentedControl
      aria-label="Вид посещаемости"
      options={[{ value: 'matrix', label: 'Таблица за период' }, { value: 'lessons', label: 'По занятиям' }, ...extraViews.map(({ value, label }) => ({ value, label }))]}
      value={view}
      onChange={setView}
    />
  )
  const extra = extraViews.find((v) => v.value === view)
  if (extra) {
    return (
      <div className="space-y-4">
        {viewSwitch}
        {extra.render()}
      </div>
    )
  }

  if (isPending) return <LoadingState label="Загружаем посещаемость…" />
  if (isError && isNotFound(error)) {
    return <EmptyState icon={Lock} title="Таблица этой группы вам недоступна" description="Ассистент видит группы, в которые назначен; Team Lead — группы своего направления." />
  }
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />

  return (
    <div className="space-y-5">
      {viewSwitch}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold text-ink">{data.group.name}</h2>
        <span className="text-sm text-ink-secondary">
          {[data.group.course, `${data.group.students_count} ${pluralize(data.group.students_count, 'студент', 'студента', 'студентов')}`].filter(Boolean).join(' · ')}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-ink-secondary">Период</span>
        {period === 'all' ? (
          <span className="flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink">
            <CalendarDays className="size-4 text-ink-muted" aria-hidden />
            {data.period.label}
          </span>
        ) : (
          <>
        <label className="relative flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink">
          <CalendarDays className="size-4 text-ink-muted" aria-hidden />
          <span className="capitalize">{data.period.label}</span>
          <input
            aria-label="Выбрать дату периода"
            type={period === 'month' ? 'month' : 'date'}
            value={period === 'month' ? date.slice(0, 7) : date}
            onChange={(e) => e.target.value && setDate(period === 'month' ? `${e.target.value}-01` : e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </label>
        <div className="flex h-10 items-center rounded-lg border border-border bg-surface">
          <button type="button" aria-label="Предыдущий период" onClick={() => setDate(data.period.prev)} className="flex h-full w-10 items-center justify-center text-ink-secondary hover:bg-surface-hover">
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <button type="button" aria-label="Следующий период" onClick={() => setDate(data.period.next)} className="flex h-full w-10 items-center justify-center border-l border-border text-ink-secondary hover:bg-surface-hover">
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </div>
          </>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SegmentedControl aria-label="Период таблицы" options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
          {data.capabilities.can_export ? (
            <Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={exporting} onClick={() => void onExport()}>
              Экспорт
            </Button>
          ) : null}
        </div>
      </div>

      <SummaryCards data={data} />

      {data.subjects.length > 1 ? (
        <SegmentedControl
          aria-label="Предмет"
          options={[{ value: '', label: 'Все предметы' }, ...data.subjects.map((s) => ({ value: String(s.id), label: s.name }))]}
          value={subject}
          onChange={setSubject}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SearchInput value={search} onChange={setSearch} placeholder="Поиск студента" />
        <Select aria-label="Статус посещаемости" options={STATUS_FILTER} placeholder="Все статусы" value={status} onChange={(e) => setStatus(e.target.value)} />
        <Select aria-label="Домашние задания" options={HOMEWORK_FILTER} placeholder="Домашние задания: все" value={homework} onChange={(e) => setHomework(e.target.value)} />
        <Select aria-label="Предупреждения" options={LEVEL_FILTER} placeholder="Предупреждения: все" value={level} onChange={(e) => setLevel(e.target.value)} />
      </div>

      <Legend />

      {data.columns.length === 0 ? (
        <EmptyState icon={CalendarDays} title="В этом периоде нет занятий" description="Выходные и дни без занятий в таблицу не попадают." />
      ) : view === 'lessons' ? (
        <LessonsTable data={data} onOpen={setLessonOpen} dimmed={isFetching} />
      ) : rows.length === 0 ? (
        <EmptyState title="Нет студентов по выбранным фильтрам" />
      ) : (
        <MatrixTable data={data} rows={rows} onOpen={setTarget} dimmed={isFetching} />
      )}

      <LessonMarksModal data={data} rows={rows} lessonId={lessonOpen} onClose={() => setLessonOpen(null)} onOpenCell={(t) => { setLessonOpen(null); setTarget(t) }} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RankingCard data={data} />
        <AttentionCard data={data} />
      </div>

      <CellModal target={target} onClose={() => setTarget(null)} />
    </div>
  )
}

function SummaryCards({ data }: { data: GroupMatrix }) {
  const { cards, marked, hw_due, percent, absent, hw_missed } = data.summary
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard tone="green" icon={<CellIcon code="done" />} label="Посетил + сдал ДЗ" value={pct(cards.done.percent)} hint={`${cards.done.count} / ${marked}`} />
        <SummaryCard tone="yellow" icon={<CellIcon code="excused" />} label="Уважительная причина" value={pct(cards.excused.percent)} hint={`${cards.excused.count} / ${marked}`} />
        <SummaryCard tone="red" icon={<CellIcon code="absent" />} label="Отсутствовал без причины" value={pct(cards.absent.percent)} hint={`${cards.absent.count} / ${marked}`} />
        <SummaryCard tone="gray" icon={<BookX className="size-6 text-ink-secondary" aria-hidden />} label="Не сдал ДЗ" value={pct(cards.hw_missed.percent)} hint={`${cards.hw_missed.count} / ${hw_due}`} />
      </div>
      <p className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-secondary">
        <span>Общая посещаемость: <b className={percentTone(percent)}>{pct(percent)}</b></span>
        <span>Пропусков: <b className="text-ink">{absent}</b></span>
        <span>Несданных ДЗ: <b className="text-ink">{hw_missed}</b></span>
        <span>Студентов: <b className="text-ink">{data.summary.students}</b></span>
      </p>
    </div>
  )
}

const STICKY_NUM = 'sticky left-0 z-20 w-10 min-w-10 bg-surface'
const STICKY_NAME = 'sticky left-10 z-20 min-w-44 max-w-56 bg-surface border-r border-border'

function MatrixTable({ data, rows, onOpen, dimmed }: { data: GroupMatrix; rows: MatrixRow[]; onOpen: (t: CellTarget) => void; dimmed: boolean }) {
  const { columns, summary } = data
  return (
    <div className={cn('card max-h-[70vh] overflow-auto transition-opacity', dimmed && 'opacity-60')}>
      <table className="w-full border-separate border-spacing-0 text-sm">
        <thead className="sticky top-0 z-30">
          <tr className="bg-surface-muted">
            <th scope="col" className={cn(STICKY_NUM, 'z-40 bg-surface-muted px-2 py-2 text-left font-medium text-ink-secondary')}>№</th>
            <th scope="col" className={cn(STICKY_NAME, 'z-40 bg-surface-muted px-3 py-2 text-left font-medium text-ink-secondary')}>Студент</th>
            {columns.map((col) => <ColumnHead key={col.lesson_id} col={col} />)}
            {['Прис.', 'Уваж.', 'Отс.', 'ДЗ ✕', '%'].map((h, i) => (
              <th key={h} scope="col" className={cn('bg-surface-muted px-2 py-2 text-center font-medium text-ink-secondary', i === 0 && 'border-l border-border')}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.student.id} className="group/row">
              <td className={cn(STICKY_NUM, 'border-t border-border px-2 py-1.5 text-ink-muted group-hover/row:bg-surface-hover')}>{index + 1}</td>
              <td className={cn(STICKY_NAME, 'border-t px-3 py-1.5 group-hover/row:bg-surface-hover')}>
                <div className="flex min-w-0 flex-col">
                  <span className={cn('truncate font-medium', row.student.in_group ? 'text-ink' : 'text-ink-muted line-through')} title={row.student.name}>
                    {row.student.name}
                  </span>
                  {row.level || row.student.status !== 'active' ? (
                    <span className="mt-0.5 flex flex-wrap gap-1">
                      {row.level ? <WarningDot level={row.level} title={row.warnings.map((w) => w.label).join('\n')} /> : null}
                      {row.student.status !== 'active' ? <span className="text-[11px] text-ink-muted">{row.student.status_display}</span> : null}
                    </span>
                  ) : null}
                </div>
              </td>
              {row.cells.map((cell, i) => {
                const col = columns[i]
                const interactive = cell.code !== 'no_lesson' && cell.code !== 'planned'
                const label = `${row.student.name}, ${shortDate(col.date)}: ${CELL_STYLE[cell.code].label}`
                return (
                  <td key={cell.lesson_id} className="border-t border-border px-1 py-1.5 text-center group-hover/row:bg-surface-hover">
                    {interactive ? (
                      <button
                        type="button"
                        aria-label={label}
                        title={label}
                        onClick={() => onOpen({ lesson: cell.lesson_id, student: row.student.id })}
                        className="relative inline-flex rounded-md transition-transform hover:scale-110 focus-visible:outline-2 focus-visible:outline-brand-500"
                      >
                        <CellIcon code={cell.code} />
                        {cell.has_comment ? <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full border border-surface bg-info" aria-hidden /> : null}
                      </button>
                    ) : (
                      <span title={label}><CellIcon code={cell.code} /></span>
                    )}
                  </td>
                )
              })}
              <StatCell value={row.stats.present} first />
              <StatCell value={row.stats.excused} />
              <StatCell value={row.stats.absent} danger={row.stats.absent > 0} />
              <StatCell value={row.stats.hw_missed} danger={row.stats.hw_missed > 0} />
              <td className={cn('border-t border-border px-2 py-1.5 text-center font-semibold', percentTone(row.stats.percent))}>{pct(row.stats.percent)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="sticky bottom-0 z-30">
          <tr className="bg-brand-50 font-semibold text-ink">
            <td className={cn(STICKY_NUM, 'bg-brand-50 px-2 py-2.5')} />
            <td className={cn(STICKY_NAME, 'bg-brand-50 px-3 py-2.5')}>Итого по группе</td>
            {columns.map((col) => (
              <td key={col.lesson_id} className="px-1 py-2.5 text-center">{col.stats.marked ? pct(col.stats.percent) : '–'}</td>
            ))}
            <td className="border-l border-border px-2 py-2.5 text-center">{summary.present}</td>
            <td className="px-2 py-2.5 text-center">{summary.excused}</td>
            <td className="px-2 py-2.5 text-center">{summary.absent}</td>
            <td className="px-2 py-2.5 text-center">{summary.hw_missed}</td>
            <td className={cn('px-2 py-2.5 text-center', percentTone(summary.percent))}>{pct(summary.percent)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function ColumnHead({ col }: { col: MatrixColumn }) {
  const weekend = col.weekday === 'Сб' || col.weekday === 'Вс'
  const title = [col.cancelled ? 'Занятие отменено — отметки сохранены, в статистику не входят' : '', col.topic || `Занятие ${col.lesson_number}`, col.subject, col.teacher, `${col.start}–${col.end}`].filter(Boolean).join(' · ')
  return (
    <th scope="col" title={title} className={cn('min-w-12 px-1 py-2 text-center font-medium', col.cancelled ? 'bg-surface-hover text-ink-muted' : weekend ? 'bg-brand-50 text-brand-700' : 'bg-surface-muted text-ink-secondary')}>
      <span className="block text-xs">{col.weekday}</span>
      <span className={cn('block whitespace-nowrap text-xs', col.cancelled ? 'text-ink-muted line-through' : 'text-ink')}>{shortDate(col.date)}</span>
    </th>
  )
}

function StatCell({ value, first, danger }: { value: number; first?: boolean; danger?: boolean }) {
  return <td className={cn('border-t border-border px-2 py-1.5 text-center', first && 'border-l', danger ? 'font-medium text-danger' : 'text-ink')}>{value}</td>
}

function RankingCard({ data }: { data: GroupMatrix }) {
  return (
    <section className="card p-4">
      <h3 className="mb-3 flex items-center gap-2 font-semibold text-ink"><Trophy className="size-4 text-brand-500" aria-hidden />Рейтинг по посещаемости</h3>
      {data.ranking.length === 0 ? <p className="text-sm text-ink-muted">Нет отметок за период.</p> : (
        <ol className="space-y-1.5">
          {data.ranking.map((r) => (
            <li key={r.student.id} className="flex items-center gap-3 text-sm">
              <span className="w-5 text-right text-ink-muted">{r.place}</span>
              <span className="min-w-0 flex-1 truncate text-ink">{r.student.name}</span>
              <span className="text-xs text-ink-muted">ДЗ {pct(r.hw_percent)}</span>
              <span className={cn('w-12 text-right font-semibold', percentTone(r.percent))}>{pct(r.percent)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function AttentionCard({ data }: { data: GroupMatrix }) {
  const flagged = data.rows.filter((r) => r.level)
  const t = data.thresholds
  return (
    <section className="card p-4">
      <h3 className="mb-1 flex items-center gap-2 font-semibold text-ink"><AlertTriangle className="size-4 text-warning" aria-hidden />Требуют внимания</h3>
      <p className="mb-3 text-xs text-ink-muted">
        {t.consecutive_absences_warning} пропуска подряд · {t.monthly_absences_attention} за период — внимание · {t.monthly_absences_critical}+ — критично · {t.missed_homework_warning}+ несданных ДЗ
      </p>
      {flagged.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-brand-700"><Check className="size-4" aria-hidden />Предупреждений нет</p>
      ) : (
        <ul className="space-y-2">
          {flagged.map((r) => (
            <li key={r.student.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className={cn('size-2 rounded-full', LEVEL_STYLE[r.level!].dot)} aria-hidden />
              <span className="font-medium text-ink">{r.student.name}</span>
              <span className="text-ink-secondary">{r.warnings.map((w) => w.label).join(' · ')}</span>
            </li>
          ))}
        </ul>
      )}
      {data.summary.warnings.critical ? (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-danger"><X className="size-3.5" aria-hidden />Критично: {data.summary.warnings.critical}</p>
      ) : null}
    </section>
  )
}

const LESSON_TH = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-ink-muted'
const LESSON_TD = 'border-t border-border px-3 py-2.5'

/** «По занятиям»: one row per lesson of the period — the same data as the table, turned around. */
function LessonsTable({ data, onOpen, dimmed }: { data: GroupMatrix; onOpen: (lessonId: number) => void; dimmed: boolean }) {
  const columns = [...data.columns].reverse()
  return (
    <div className={cn('card overflow-x-auto transition-opacity', dimmed && 'opacity-60')}>
      <table className="w-full min-w-[860px] text-sm">
        <thead className="bg-surface-muted">
          <tr>{['Дата', 'Время', 'Предмет', 'Тема', 'Тренер', 'Прис.', 'Уваж.', 'Отс.', 'Нет данных', 'ДЗ ✕', '%'].map((h) => <th key={h} className={LESSON_TH}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {columns.map((col) => (
            <tr key={col.lesson_id} className={cn('cursor-pointer hover:bg-surface-hover', col.cancelled && 'text-ink-muted')} onClick={() => onOpen(col.lesson_id)}>
              <td className={LESSON_TD}>
                <button type="button" className="whitespace-nowrap font-medium text-brand-700 hover:underline" onClick={(e) => { e.stopPropagation(); onOpen(col.lesson_id) }}>
                  {col.weekday}, {shortDate(col.date)}
                </button>
                {col.cancelled ? <span className="block text-xs">отменено</span> : !col.held ? <span className="block text-xs text-ink-muted">впереди</span> : null}
              </td>
              <td className={cn(LESSON_TD, 'whitespace-nowrap tabular-nums')}>{col.start}–{col.end}</td>
              <td className={LESSON_TD}>{col.subject || '—'}</td>
              <td className={cn(LESSON_TD, 'max-w-56 truncate')} title={col.topic}>{col.topic || `Занятие ${col.lesson_number}`}</td>
              <td className={cn(LESSON_TD, 'text-ink-secondary')}>{col.teacher || '—'}</td>
              <td className={LESSON_TD}>{col.stats.present}</td>
              <td className={LESSON_TD}>{col.stats.excused}</td>
              <td className={cn(LESSON_TD, col.stats.absent ? 'font-medium text-danger' : '')}>{col.stats.absent}</td>
              <td className={cn(LESSON_TD, col.stats.unmarked ? 'text-warning' : 'text-ink-muted')}>{col.stats.unmarked}</td>
              <td className={LESSON_TD}>{col.has_homework ? col.stats.hw_missed : '—'}</td>
              <td className={cn(LESSON_TD, 'font-semibold', percentTone(col.stats.percent))}>{col.stats.marked ? pct(col.stats.percent) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Every student's mark on one lesson; a student opens the cell (reason, comment, history). */
function LessonMarksModal({ data, rows, lessonId, onClose, onOpenCell }: {
  data: GroupMatrix
  rows: MatrixRow[]
  lessonId: number | null
  onClose: () => void
  onOpenCell: (target: CellTarget) => void
}) {
  const index = data.columns.findIndex((c) => c.lesson_id === lessonId)
  const col = index >= 0 ? data.columns[index] : null
  return (
    <Modal isOpen={col !== null} onClose={onClose} title={col ? `${col.weekday}, ${shortDate(col.date)} · ${col.subject || 'Занятие'}` : ''} size="lg">
      {col ? (
        <div className="space-y-3">
          <p className="text-sm text-ink-secondary">
            {[col.topic || `Занятие ${col.lesson_number}`, col.teacher, `${col.start}–${col.end}`, col.cancelled ? 'занятие отменено' : ''].filter(Boolean).join(' · ')}
          </p>
          <ul className="divide-y divide-border">
            {rows.map((row) => {
              const cell = row.cells[index]
              const interactive = cell.code !== 'no_lesson' && cell.code !== 'planned'
              return (
                <li key={row.student.id}>
                  <button
                    type="button"
                    disabled={!interactive}
                    onClick={() => onOpenCell({ lesson: col.lesson_id, student: row.student.id })}
                    className="flex w-full items-center gap-3 py-2 text-left text-sm enabled:hover:bg-surface-hover disabled:cursor-default"
                  >
                    <CellIcon code={cell.code} size="sm" />
                    <span className="min-w-0 flex-1 truncate text-ink">{row.student.name}</span>
                    <span className="text-ink-secondary">{CELL_STYLE[cell.code].label}</span>
                    {cell.homework !== 'none' ? <span className="w-28 text-right text-xs text-ink-muted">ДЗ: {HOMEWORK_LABEL[cell.homework].toLowerCase()}</span> : <span className="w-28" />}
                    {cell.has_comment ? <span className="size-2 rounded-full bg-info" title="Есть комментарий или причина" /> : null}
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </Modal>
  )
}
