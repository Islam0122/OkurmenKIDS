import { useState } from 'react'

import { Drawer } from '@/components/ui/Drawer'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { formatDuration } from '@/features/exams/examUi'
import { useGroupDetail, useGroupStats, useTeacherPerformance, useTrainerDetail, useTrainerStats } from '@/hooks/useMonitoring'
import type { MonitoringFilters, StatRow } from '@/types/monitoring'

import { percent } from './monitoringUi'

const STAT_HEAD = ['Студентов', 'Попыток', 'Сейчас', 'Завершено', 'Сдали', 'Средний балл', 'Нарушения', 'Ср. время'] as const

function StatCells({ row }: { row: StatRow }) {
  return (
    <>
      <td className="px-4 py-3 text-right">{row.students}</td>
      <td className="px-4 py-3 text-right">{row.attempts}</td>
      <td className="px-4 py-3 text-right">{row.active}</td>
      <td className="px-4 py-3 text-right">{row.completed}</td>
      <td className="px-4 py-3 text-right">{percent(row.pass_rate)}</td>
      <td className="px-4 py-3 text-right font-semibold">{percent(row.average_score)}</td>
      <td className={`px-4 py-3 text-right ${row.violations ? 'text-danger' : 'text-ink-muted'}`}>{row.violations}</td>
      <td className="px-4 py-3 text-right font-mono">{formatDuration(row.avg_duration_seconds)}</td>
    </>
  )
}

function StatTable<T extends StatRow>({ title, rows, name, onOpen, label }: {
  title: string
  rows: T[]
  name: (row: T) => string
  onOpen?: (row: T) => void
  label: string
}) {
  return (
    <div className="card overflow-hidden">
      <div className="scroll-x">
        <table className="w-full min-w-[860px] text-left text-sm" aria-label={label}>
          <thead className="bg-surface-hover text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-medium">{title}</th>
              {STAT_HEAD.map((h) => <th key={h} className="px-4 py-2 text-right font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={name(row)} className="border-t border-border">
                <td className="px-4 py-3 font-medium text-ink">
                  {onOpen ? <button type="button" className="text-left text-brand-700 hover:underline" onClick={() => onOpen(row)}>{name(row)}</button> : name(row)}
                </td>
                <StatCells row={row} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function TeachersTab({ filters }: { filters: MonitoringFilters }) {
  const { data, isLoading, isError, refetch } = useTeacherPerformance({ ...filters, page: undefined }, true)
  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!data?.length) return <EmptyState title="Нет данных" />
  return <StatTable title="Тренер" label="Эффективность тренеров" rows={data} name={(r) => r.teacher.name} />
}

export function GroupsTab({ filters }: { filters: MonitoringFilters }) {
  const { data, isLoading, isError, refetch } = useGroupStats({ ...filters, page: undefined })
  const [openId, setOpenId] = useState<number | null>(null)
  const detail = useGroupDetail(openId)
  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!data?.length) return <EmptyState title="Нет данных" />
  return (
    <>
      <StatTable title="Группа" label="Аналитика групп" rows={data} name={(r) => r.group.name} onOpen={(r) => setOpenId(r.group.id)} />
      <Drawer isOpen={openId !== null} onClose={() => setOpenId(null)} title={detail.data?.group.name ?? 'Группа'} side="right" size="lg">
        {detail.isLoading || !detail.data ? <LoadingState /> : (
          <div className="space-y-5 text-sm">
            <dl className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Средний балл</dt><dd className="mt-1 text-lg font-semibold">{percent(detail.data.average_score)}</dd></div>
              <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Сдали</dt><dd className="mt-1 text-lg font-semibold">{percent(detail.data.pass_rate)}</dd></div>
              <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Активные экзамены</dt><dd className="mt-1 text-lg font-semibold">{detail.data.active_exams}</dd></div>
              <div className="rounded-lg bg-surface-hover p-3"><dt className="text-ink-muted">Ср. время</dt><dd className="mt-1 font-mono text-lg font-semibold">{formatDuration(detail.data.avg_duration_seconds)}</dd></div>
            </dl>
            {detail.data.failed_students.length ? (
              <p className="rounded-lg bg-danger-soft px-3 py-2 text-danger">Не сдали: {detail.data.failed_students.join(', ')}</p>
            ) : null}
            <table className="w-full text-left" aria-label="Студенты группы">
              <thead className="text-xs uppercase text-ink-muted"><tr><th className="py-1">Студент</th><th className="py-1 text-right">Попыток</th><th className="py-1 text-right">Средний</th><th className="py-1 text-right">Нарушения</th></tr></thead>
              <tbody>
                {detail.data.students_list.map((s) => (
                  <tr key={s.student_name} className="border-t border-border">
                    <td className="py-2">{s.student_name}</td>
                    <td className="py-2 text-right">{s.attempts}</td>
                    <td className="py-2 text-right">{percent(s.average_score)}</td>
                    <td className={`py-2 text-right ${s.violations ? 'text-danger' : 'text-ink-muted'}`}>{s.violations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Drawer>
    </>
  )
}

export function TrainersTab({ filters }: { filters: MonitoringFilters }) {
  const { data, isLoading, isError, refetch } = useTrainerStats({ ...filters, page: undefined })
  const [openId, setOpenId] = useState<string | null>(null)
  const detail = useTrainerDetail(openId)
  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!data?.length) return <EmptyState title="Нет данных" />
  return (
    <>
      <StatTable title="Тренажёр / экзамен" label="Аналитика тренажёров" rows={data}
        name={(r) => `${r.mode === 'exam' ? 'Экзамен' : 'Тренажёр'}: ${r.session.title}`} onOpen={(r) => setOpenId(r.session.id)} />
      <Drawer isOpen={openId !== null} onClose={() => setOpenId(null)} title={detail.data?.session.title ?? 'Аналитика'} side="right" size="lg">
        {detail.isLoading || !detail.data ? <LoadingState /> : (
          <section>
            <h3 className="section-title mb-3">Сложные вопросы</h3>
            {detail.data.difficult_questions.length ? (
              <ol className="space-y-3" aria-label="Сложные вопросы">
                {detail.data.difficult_questions.map((q) => (
                  <li key={q.question_id} className="text-sm">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="min-w-0 text-ink"><span className="font-semibold">Вопрос {q.number}.</span> {q.text}</span>
                      <span className="shrink-0 text-xs text-ink-muted">{q.answered} ответов</span>
                    </div>
                    <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-danger-soft" role="img" aria-label={`Верно ${q.correct_rate}%, неверно ${q.incorrect_rate}%`}>
                      <div className="bg-brand-500" style={{ width: `${q.correct_rate}%` }} />
                    </div>
                    <div className="mt-1 flex justify-between text-xs"><span className="text-brand-700">Верно {q.correct_rate}%</span><span className="text-danger">Неверно {q.incorrect_rate}%</span></div>
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-ink-muted">Пока нет проверенных ответов.</p>}
          </section>
        )}
      </Drawer>
    </>
  )
}
