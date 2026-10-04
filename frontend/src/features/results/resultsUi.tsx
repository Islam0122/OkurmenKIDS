import { useState } from 'react'
import { Award, BarChart3, CheckCircle2, ClipboardList, Download, Trophy, Users, XCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { monitoringApi } from '@/api/monitoring'
import { TrendChart } from '@/components/charts/TrendChart'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DataTable, type DataTableColumn } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useToast } from '@/components/ui/Toast'
import { formatDuration } from '@/features/exams/examUi'
import { AttemptDrawer } from '@/features/monitoring/AttemptDrawer'
import { formatTime, percent } from '@/features/monitoring/monitoringUi'
import { useResultBreakdown, useResults, useResultStudents, useResultsSummary } from '@/hooks/useResults'
import type { MonitoringAttempt, MonitoringFilters, ResultBreakdownBy, ResultsSummary, StudentResultRow } from '@/types/monitoring'

export const NO_RESULTS = 'Азырынча тесттин жыйынтыгы жок'
const PAGE_SIZE = 25

export function ResultBadge({ passed }: { passed: boolean | null | undefined }) {
  if (passed === null || passed === undefined) return <Badge tone="info">В процессе</Badge>
  return passed
    ? <Badge tone="success"><CheckCircle2 className="h-3 w-3" aria-hidden="true" />Сдал</Badge>
    : <Badge tone="danger"><XCircle className="h-3 w-3" aria-hidden="true" />Не сдал</Badge>
}

/** Summary cards for any scope: a student, a group, a teacher, a session… */
export function ResultsSummaryCards({ summary, variant = 'full' }: { summary: ResultsSummary; variant?: 'full' | 'compact' | 'group' }) {
  const s = summary
  const correct = s.average_correct !== null && s.average_questions !== null ? `${s.average_correct} / ${s.average_questions}` : '—'
  if (variant === 'compact') {
    return (
      <StatGrid>
        <StatCard label="Протестировано студентов" value={s.students_tested} icon={Users} />
        <StatCard label="Попыток" value={s.attempts} icon={ClipboardList} />
        <StatCard label="Средний результат" value={percent(s.average_score)} icon={BarChart3} />
        <StatCard label="Сдали" value={percent(s.pass_rate)} icon={CheckCircle2} hint={`${s.passed} из ${s.attempts}`} />
      </StatGrid>
    )
  }
  return (
    <StatGrid>
      {variant === 'group' && s.students_total !== undefined ? (
        <StatCard label="Студентов в группе" value={s.students_total} icon={Users} hint={`прошли тесты: ${s.students_tested}`} />
      ) : (
        <StatCard label="Протестировано студентов" value={s.students_tested} icon={Users} />
      )}
      <StatCard label="Средний результат" value={percent(s.average_score)} icon={BarChart3}
        hint={s.best_score !== null ? `лучший ${percent(s.best_score)} · минимум ${percent(s.lowest_score)}` : undefined} />
      <StatCard label="Успешность" value={percent(s.pass_rate)} icon={CheckCircle2} hint={`сдали ${s.passed} · не сдали ${s.failed}`}
        tone={s.pass_rate !== null && s.pass_rate < 50 ? 'warning' : 'default'} />
      <StatCard label="Попыток" value={s.attempts} icon={ClipboardList} hint={`правильных в среднем: ${correct}`} />
    </StatGrid>
  )
}

export function ResultsDynamics({ summary, title = 'Динамика результатов' }: { summary: ResultsSummary; title?: string }) {
  const points = summary.dynamics
    .filter((p) => p.average_score !== null)
    .map((p) => ({ label: p.date.slice(5).split('-').reverse().join('.'), value: p.average_score as number }))
  if (points.length < 2) return null
  // The SVG scales with its width — keep it to a readable size.
  return <div className="max-w-2xl"><TrendChart title={title} points={points} max={100} valueSuffix="%" /></div>
}

/** Summary + best student / group (teacher page, dashboard). */
export function ResultsOverview({ filters, title = 'Результаты учеников', variant = 'full' }: { filters: MonitoringFilters; title?: string; variant?: 'full' | 'compact' }) {
  const { data, isLoading, isError, refetch } = useResultsSummary(filters)
  return (
    <section className="space-y-4" aria-label={title}>
      <h2 className="section-title">{title}</h2>
      {isLoading ? <LoadingState /> : isError || !data ? <ErrorState onRetry={() => void refetch()} /> : !data.attempts ? (
        <EmptyState icon={ClipboardList} title={NO_RESULTS} description="Здесь появятся результаты тестов студентов." />
      ) : (
        <>
          <ResultsSummaryCards summary={data} variant={variant} />
          {variant === 'full' ? (
            <StatGrid columns={3}>
              <StatCard label="Групп / тестов" value={`${data.groups} / ${data.tests}`} icon={ClipboardList} />
              <StatCard label="Лучший студент" value={data.best_student?.name ?? '—'} icon={Trophy}
                hint={data.best_student ? `средний ${percent(data.best_student.average_score)}` : undefined} />
              <StatCard label="Лучшая группа" value={data.best_group?.name ?? '—'} icon={Award}
                hint={data.best_group ? `средний ${percent(data.best_group.average_score)}` : undefined} />
            </StatGrid>
          ) : null}
        </>
      )}
    </section>
  )
}

type Column = 'student' | 'group' | 'teacher' | 'test' | 'subject' | 'attempt'

/** Paginated results with «Подробнее» (the detailed drawer). */
export function ResultsTable({ filters, columns = ['student', 'group', 'teacher', 'test', 'subject'], title = 'Результаты тестов', exportable = false }: {
  filters: MonitoringFilters
  columns?: Column[]
  title?: string
  exportable?: boolean
}) {
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const { showToast } = useToast()
  const query = { ...filters, page, page_size: PAGE_SIZE }
  const { data, isLoading, isError, refetch } = useResults(query)
  const show = (c: Column) => columns.includes(c)

  const cols: DataTableColumn<MonitoringAttempt>[] = [
    ...(show('student') ? [{ key: 'student', header: 'Студент', render: (r: MonitoringAttempt) => <span className="font-medium text-ink">{r.student_name}</span> }] : []),
    ...(show('test') ? [{ key: 'test', header: 'Тест', render: (r: MonitoringAttempt) => r.test.title }] : []),
    ...(show('subject') ? [{ key: 'subject', header: 'Предмет', render: (r: MonitoringAttempt) => r.test.subject || '—' }] : []),
    ...(show('group') ? [{ key: 'group', header: 'Группа', render: (r: MonitoringAttempt) => r.group?.name ?? '—' }] : []),
    ...(show('teacher') ? [{ key: 'teacher', header: 'Тренер', render: (r: MonitoringAttempt) => r.teacher?.name ?? '—' }] : []),
    { key: 'answers', header: 'Ответы', render: (r) => <span title="правильно / неправильно / вопросов"><span className="text-success">{r.correct_count ?? '—'}</span> / <span className="text-danger">{r.incorrect_count ?? '—'}</span> / {r.question_total}</span> },
    { key: 'score', header: 'Балл', render: (r) => <span className="font-semibold">{percent(r.score)}</span> },
    { key: 'status', header: 'Статус', render: (r) => <ResultBadge passed={r.passed} /> },
    { key: 'time', header: 'Время', render: (r) => formatDuration(r.duration_seconds) },
    ...(show('attempt') ? [{ key: 'attempt', header: '№', render: (r: MonitoringAttempt) => r.attempt_no ?? '—' }] : []),
    { key: 'date', header: 'Дата', render: (r) => formatTime(r.finished_at) },
    { key: 'open', header: '', render: (r) => <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setOpenId(r.id) }}>Подробнее</Button> },
  ]

  async function download() {
    setExporting(true)
    try {
      await monitoringApi.exportResults(filters)
    } catch {
      showToast('Не удалось выгрузить результаты', 'error')
    } finally {
      setExporting(false)
    }
  }

  return (
    <section className="space-y-3" aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">{title}</h2>
        {exportable && data?.count ? (
          <Button size="sm" variant="secondary" leftIcon={<Download className="h-4 w-4" />} onClick={() => void download()} disabled={exporting}>
            Excel
          </Button>
        ) : null}
      </div>
      {isLoading ? <LoadingState /> : isError || !data ? <ErrorState onRetry={() => void refetch()} /> : !data.results.length ? (
        <EmptyState icon={ClipboardList} title={NO_RESULTS} description="Результат появится после того, как студент завершит тест." />
      ) : (
        <>
          <DataTable columns={cols} rows={data.results} getRowKey={(r) => r.id} onRowClick={(r) => setOpenId(r.id)} />
          <Pagination page={page} pageSize={PAGE_SIZE} totalCount={data.count} onPageChange={setPage} />
        </>
      )}
      <AttemptDrawer attemptId={openId} onClose={() => setOpenId(null)} />
    </section>
  )
}

/** One row per student (group «Тестирование» tab). Click → student page. */
export function StudentResultsTable({ filters }: { filters: MonitoringFilters }) {
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useResultStudents(filters)
  const cols: DataTableColumn<StudentResultRow>[] = [
    { key: 'student', header: 'Студент', render: (r) => <span className="font-medium text-ink">{r.student.name}</span> },
    { key: 'attempts', header: 'Попыток', render: (r) => r.attempts },
    { key: 'average', header: 'Средний', render: (r) => percent(r.average_score) },
    { key: 'best', header: 'Лучший', render: (r) => percent(r.best_score) },
    { key: 'last', header: 'Последний', render: (r) => percent(r.last_score) },
    { key: 'status', header: 'Статус', render: (r) => <ResultBadge passed={r.last_passed} /> },
  ]
  return (
    <section className="space-y-3" aria-label="Студенты">
      <h2 className="section-title">Студенты</h2>
      {isLoading ? <LoadingState /> : isError || !data ? <ErrorState onRetry={() => void refetch()} /> : !data.length ? (
        <EmptyState icon={Users} title={NO_RESULTS} />
      ) : (
        <DataTable columns={cols} rows={data} getRowKey={(r) => r.student.id} onRowClick={(r) => navigate(`/app/students/${r.student.id}`)} />
      )}
    </section>
  )
}

/** Short list of the latest results (dashboards). */
export function RecentResults({ filters, title = 'Акыркы жыйынтыктар', limit = 5 }: { filters: MonitoringFilters; title?: string; limit?: number }) {
  const [openId, setOpenId] = useState<string | null>(null)
  const { data, isLoading, isError, refetch } = useResults({ ...filters, page: 1, page_size: limit })
  return (
    <Card title={title}>
      {isLoading ? <LoadingState /> : isError || !data ? <ErrorState onRetry={() => void refetch()} /> : !data.results.length ? (
        <p className="py-4 text-center text-sm text-ink-muted">{NO_RESULTS}</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.results.map((r) => (
            <li key={r.id}>
              <button type="button" onClick={() => setOpenId(r.id)} className="flex w-full min-w-0 items-center justify-between gap-3 py-2.5 text-left hover:bg-surface-hover">
                <span className="min-w-0">
                  <span className="block truncate font-medium text-ink">{r.test.title}</span>
                  <span className="block truncate text-xs text-ink-muted">{r.student_name}{r.group ? ` · ${r.group.name}` : ''} · {formatTime(r.finished_at)}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="font-semibold text-ink">{percent(r.score)}</span>
                  <ResultBadge passed={r.passed} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <AttemptDrawer attemptId={openId} onClose={() => setOpenId(null)} />
    </Card>
  )
}

const BREAKDOWN_TITLE: Record<ResultBreakdownBy, string> = { group: 'По группам', subject: 'По предметам', teacher: 'По тренерам', test: 'По тестам' }

export function ResultsBreakdown({ filters, by }: { filters: MonitoringFilters; by: ResultBreakdownBy }) {
  const { data, isLoading, isError } = useResultBreakdown(filters, by)
  return (
    <Card title={BREAKDOWN_TITLE[by]}>
      {isLoading ? <LoadingState /> : isError || !data ? <p className="text-sm text-ink-muted">Нет данных</p> : !data.length ? (
        <p className="py-2 text-sm text-ink-muted">{NO_RESULTS}</p>
      ) : (
        <ul className="space-y-2">
          {data.map((row) => (
            <li key={row.id} className="flex min-w-0 items-center gap-3 text-sm">
              <span className="min-w-0 flex-1 truncate text-ink" title={row.name}>{row.name}</span>
              <span className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-surface-hover" aria-hidden="true">
                <span className="block h-full rounded-full bg-brand-500" style={{ width: `${row.average_score ?? 0}%` }} />
              </span>
              <span className="w-12 shrink-0 text-right font-semibold text-ink">{percent(row.average_score)}</span>
              <span className="w-20 shrink-0 text-right text-xs text-ink-muted">{row.attempts} попыт.</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
