import { useState } from 'react'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useToast } from '@/components/ui/Toast'
import { useConfirmHistory, useGroupAcademicProgress } from '@/hooks/useAcademicProgress'
import { extractErrorMessage } from '@/lib/apiError'
import type { AcademicProgress } from '@/types/academicProgress'
import { cn } from '@/utils/cn'

function Bar({ value, className }: { value: number | null; className?: string }) {
  return (
    <div className={cn('h-1.5 overflow-hidden rounded-full bg-surface-hover', className)}>
      <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(value ?? 0, 100)}%` }} />
    </div>
  )
}

function tooltip(p: AcademicProgress): string {
  if (!p.month || !p.course) return p.reason || p.status_display
  return [
    `${p.month.label}${p.month.subject ? ` · ${p.month.subject.name}` : ''}`,
    `Проведено ${p.month.done} из ${p.month.planned}, осталось ${p.month.remaining}`,
    p.month.next_lesson ? `Следующее — ${p.month.next_lesson}-е занятие месяца` : 'Курс пройден',
    `Курс: ${p.course.done} / ${p.course.planned}`,
    p.lessons_before_lms ? `Из них до LMS: ${p.lessons_before_lms}` : '',
  ].filter(Boolean).join('\n')
}

/** «2-й месяц · 3 / 12 занятий» with a small bar — the «Пройдено» cell of group tables. */
export function StudyMonthCell({ progress, settingsPath }: { progress: AcademicProgress; settingsPath?: string }) {
  if (progress.status === 'needs_setup' || !progress.month) {
    const badge = (
      <span title={progress.reason} className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">
        <AlertTriangle className="size-3.5" aria-hidden />Требуется настройка
      </span>
    )
    return settingsPath ? <Link to={settingsPath}>{badge}</Link> : badge
  }
  const m = progress.month
  return (
    <div className="min-w-28" title={tooltip(progress)}>
      <p className="whitespace-nowrap text-sm font-semibold text-ink">{progress.status === 'completed' ? 'Курс пройден' : m.label}</p>
      <p className="whitespace-nowrap text-xs tabular-nums text-ink-secondary">{m.done} / {m.planned} занятий</p>
      <Bar value={m.progress} className="my-1 w-28" />
      <p className="whitespace-nowrap text-xs text-ink-muted">
        {[m.subject?.name, progress.status !== 'completed' ? `осталось ${m.remaining}` : ''].filter(Boolean).join(' · ')}
      </p>
    </div>
  )
}

/** «Общий прогресс курса» — by the study months when set up, else the old plan. */
export function CourseProgressCell({ progress, legacy }: { progress: AcademicProgress; legacy: { completed: number; planned: number } }) {
  const c = progress.course
  const done = c ? c.done : legacy.completed
  const planned = c ? c.planned : legacy.planned
  const value = planned ? Math.round((done / planned) * 1000) / 10 : null
  return (
    <div className="min-w-24" title={c ? `По плану занятий программы: ${legacy.completed} / ${legacy.planned || '—'}` : 'По плану занятий программы (учебные месяцы не настроены)'}>
      <p className="text-sm tabular-nums text-ink">{done}{planned ? <span className="text-xs text-ink-muted"> / {planned}</span> : null}</p>
      <Bar value={value} className="mt-1 w-24" />
    </div>
  )
}

/** A group's study months, its students' own progress in the current month,
 * and — when the first lessons are missing from the LMS — the confirmation. */
export function GroupStudyMonths({ groupId, settingsPath }: { groupId: number; settingsPath?: string }) {
  const { data, isPending, isError, refetch } = useGroupAcademicProgress(groupId)
  if (isPending) return <LoadingState label="Считаем учебные месяцы…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />
  const p = data.progress
  return (
    <div className="space-y-4">
      {p.status === 'needs_setup' ? (
        <div className="rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning">
          <p className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4" aria-hidden />Требуется настройка</p>
          <p className="mt-1">{p.reason}</p>
          {!p.configured && settingsPath ? <Link to={settingsPath} className="mt-2 inline-block font-medium underline">Настроить учебные месяцы программы</Link> : null}
          {p.configured && data.can_edit ? <HistoryForm groupId={groupId} inLms={p.lessons_in_lms} /> : null}
        </div>
      ) : (
        <>
          <p className="text-sm text-ink-secondary">
            {p.status_display} · курс {p.course?.done} / {p.course?.planned} занятий
            {p.lessons_before_lms ? ` (из них ${p.lessons_before_lms} до LMS)` : ''}
          </p>
          <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {p.months.map((m) => (
              <li key={m.number} className={cn('rounded-lg border px-3 py-2', m.state === 'current' ? 'border-brand-500 bg-brand-50' : 'border-border')}>
                <p className="flex items-center justify-between text-xs text-ink-muted">
                  {m.number}-й месяц
                  {m.state === 'done' ? <CheckCircle2 className="size-3.5 text-brand-500" aria-label="пройден" /> : null}
                </p>
                <p className="truncate text-sm font-medium text-ink">{m.subject?.name ?? '—'}</p>
                <p className="text-xs tabular-nums text-ink-secondary">{m.done} / {m.planned}</p>
                <Bar value={m.progress} className="mt-1" />
              </li>
            ))}
          </ol>
          {data.students.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-ink-muted">
                    <th className="py-2 font-medium">Студент</th>
                    <th className="py-2 font-medium">В текущем месяце</th>
                    <th className="py-2 font-medium">За курс</th>
                  </tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.id} className="border-t border-border">
                      <td className="py-2 text-ink">{s.name}</td>
                      <td className="py-2 tabular-nums">{s.month_attended} из {s.month_held}{s.month_rate !== null ? <span className="text-ink-muted"> · {s.month_rate}%</span> : null}</td>
                      <td className="py-2 tabular-nums">{s.course_attended} из {s.course_held}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-ink-muted">Прогресс студента — посещённые им занятия; прогресс группы — проведённые занятия, пропуски его не уменьшают.</p>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}

function HistoryForm({ groupId, inLms }: { groupId: number; inLms: number }) {
  const [value, setValue] = useState('')
  const save = useConfirmHistory(groupId)
  const { showToast } = useToast()
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2 text-ink"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(Number(value), {
          onSuccess: () => showToast('История группы подтверждена', 'success'),
          onError: (error) => showToast(extractErrorMessage(error, 'Не удалось сохранить'), 'error'),
        })
      }}
    >
      <label className="text-sm">
        <span className="mb-1 block">Проведено занятий до LMS (в LMS — {inLms})</span>
        <input type="number" min={0} max={2000} required className="form-control w-32" value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <Button type="submit" size="sm" isLoading={save.isPending}>Подтвердить</Button>
    </form>
  )
}
