import { useState } from 'react'
import type { ReactNode } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { ChevronRight, ClipboardCheck, NotebookPen } from 'lucide-react'

import type { RecordFilters } from '@/api/assistant'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useGroupAttendance, useGroupHomework } from '@/hooks/useAssistant'
import type { GroupDetail } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { useAssistantActions } from '../actions/AssistantActions'
import { AttendanceBadge, HomeworkStateBadge, Percent, PercentBar } from './badges'

/**
 * The group's «Посещаемость» and «ДЗ» tabs for the Assistant — read only:
 * summary → compact filters → table → a click opens the details. There is
 * no «Отметить», no edit, no status change anywhere here.
 */

type Period = NonNullable<RecordFilters['period']>
const PERIODS: { value: Period; label: string }[] = [
  { value: 'today', label: 'Сегодня' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'all', label: 'Всё время' },
  { value: 'custom', label: 'Период' },
]
const day = (value: string) => format(parseISO(value), 'd MMM', { locale: ru })

function useFilters() {
  const [filters, setFilters] = useState<RecordFilters>({ period: 'all' })
  const set = (patch: Partial<RecordFilters>) => setFilters((f) => ({ ...f, ...patch }))
  const query: RecordFilters = { ...filters, start: filters.period === 'custom' ? filters.start : undefined, end: filters.period === 'custom' ? filters.end : undefined }
  return { filters, set, query }
}

function FiltersRow({ filters, set, children }: { filters: RecordFilters; set: (p: Partial<RecordFilters>) => void; children?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <SegmentedControl aria-label="Период" options={PERIODS} value={filters.period ?? 'all'} onChange={(period) => set({ period })} />
      {filters.period === 'custom' ? (
        <div className="flex items-center gap-1">
          <DatePicker aria-label="С" value={filters.start ?? ''} onChange={(e) => set({ start: e.target.value || undefined })} className="w-40" />
          <span className="text-ink-muted">—</span>
          <DatePicker aria-label="По" value={filters.end ?? ''} onChange={(e) => set({ end: e.target.value || undefined })} className="w-40" />
        </div>
      ) : null}
      {children}
    </div>
  )
}

function teacherOptions(group: GroupDetail) {
  const seen = new Map<number, string>()
  group.programs.forEach((p) => seen.set(p.teacher.id, p.teacher.name))
  return [...seen].map(([id, name]) => ({ value: String(id), label: name }))
}

function Kpi({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface px-3 py-2">
      <p className="truncate text-2xs text-ink-secondary">{label}</p>
      <p className={cn('text-lg leading-tight font-semibold tabular-nums', tone ?? 'text-ink')}>{value}</p>
    </div>
  )
}

export function GroupAttendanceTab({ group }: { group: GroupDetail }) {
  const { open } = useAssistantActions()
  const { filters, set, query } = useFilters()
  const { data, isPending, isError, refetch } = useGroupAttendance(group.id, query)
  const s = data?.summary
  const studentOptions = group.students.filter((st) => st.status === 'active').map((st) => ({ value: String(st.id), label: st.full_name }))
  const problem = data?.students.filter((st) => st.marked && ((st.percent ?? 100) < 80 || st.consecutive_absences >= 2)) ?? []

  return (
    <div className="space-y-4">
      <section className="card card-body">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div className="min-w-44 flex-1">
            <p className="text-sm text-ink-secondary">Посещаемость</p>
            <p className="text-3xl leading-tight font-semibold"><Percent value={s?.percent ?? null} /></p>
            <PercentBar value={s?.percent ?? null} className="mt-2 max-w-md" />
          </div>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div><dt className="text-ink-secondary">Присутствовали</dt><dd className="font-semibold text-ink tabular-nums">{s?.attended ?? '—'}</dd></div>
            <div><dt className="text-ink-secondary">Пропуски</dt><dd className="font-semibold text-danger tabular-nums">{s?.absent ?? '—'}</dd></div>
            <div><dt className="text-ink-secondary">Опоздания</dt><dd className="font-semibold text-warning tabular-nums">{s?.late ?? '—'}</dd></div>
            <div><dt className="text-ink-secondary">Всего отметок</dt><dd className="font-semibold text-ink tabular-nums">{s?.marked ?? '—'}</dd></div>
            {s?.unmarked ? <div><dt className="text-ink-secondary">Не отмечено</dt><dd className="font-semibold text-ink-muted tabular-nums">{s.unmarked}</dd></div> : null}
          </dl>
        </div>
      </section>

      <FiltersRow filters={filters} set={set}>
        <div className="w-full sm:w-48"><Select aria-label="Студент" value={filters.student ? String(filters.student) : ''} placeholder="Все студенты"
          onChange={(e) => set({ student: e.target.value ? Number(e.target.value) : undefined })} options={studentOptions} /></div>
        <div className="w-full sm:w-44"><Select aria-label="Тренер" value={filters.teacher ? String(filters.teacher) : ''} placeholder="Все тренеры"
          onChange={(e) => set({ teacher: e.target.value ? Number(e.target.value) : undefined })} options={teacherOptions(group)} /></div>
        <div className="w-full sm:w-44"><Select aria-label="Статус" value={filters.status ?? ''} placeholder="Все статусы"
          onChange={(e) => set({ status: e.target.value || undefined })}
          options={[{ value: 'present', label: 'Присутствовал' }, { value: 'absent', label: 'Отсутствовал' }, { value: 'late', label: 'Опоздал' }, { value: 'unmarked', label: 'Не отмечен' }]} /></div>
      </FiltersRow>

      {isPending ? <LoadingState label="Загружаем посещаемость…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <section className="card min-w-0 overflow-hidden">
            <h3 className="border-b border-border px-4 py-2.5 text-sm font-semibold text-ink">Проведённые занятия · {data.lessons.length}</h3>
            {data.lessons.length === 0 ? <EmptyState icon={ClipboardCheck} title="Занятий за период нет" className="py-8" /> : (
              <div className="max-h-[32rem] overflow-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="sticky top-0 z-10 bg-surface-muted text-left text-xs text-ink-secondary">
                    <tr>
                      <th className="px-4 py-2 font-medium">Дата</th><th className="px-2 py-2 font-medium">Занятие</th><th className="px-2 py-2 font-medium">Тренер</th>
                      {filters.student ? <th className="px-2 py-2 font-medium">Статус</th> : (
                        <><th className="px-2 py-2 text-right font-medium">Были</th><th className="px-2 py-2 text-right font-medium">Нет</th><th className="px-4 py-2 text-right font-medium">%</th></>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {data.lessons.map((l) => (
                      <tr key={l.id} onClick={() => open({ type: 'lesson-detail', lessonId: l.id })} className="cursor-pointer hover:bg-surface-hover">
                        <td className="px-4 py-2 whitespace-nowrap text-ink">{day(l.date)}</td>
                        <td className="max-w-56 px-2 py-2"><span className="block truncate text-ink">Занятие {l.lesson_number}</span><span className="block truncate text-xs text-ink-muted">{l.topic || l.subject?.name}</span></td>
                        <td className="max-w-40 truncate px-2 py-2 text-ink-secondary">{l.teacher?.name ?? '—'}</td>
                        {filters.student ? <td className="px-2 py-2"><AttendanceBadge status={l.student_status} /></td> : (
                          <>
                            <td className="px-2 py-2 text-right text-ink tabular-nums">{l.attended}</td>
                            <td className={cn('px-2 py-2 text-right tabular-nums', l.absent ? 'text-danger' : 'text-ink-muted')}>{l.absent}{l.unmarked ? <span className="block text-2xs text-ink-muted">не отм. {l.unmarked}</span> : null}</td>
                            <td className="px-4 py-2 text-right"><Percent value={l.percent} /></td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card min-w-0 overflow-hidden">
            <h3 className="border-b border-border px-4 py-2.5 text-sm font-semibold text-ink">Студенты {problem.length ? <span className="text-danger">· часто пропускают {problem.length}</span> : null}</h3>
            <ul className="max-h-[32rem] divide-y divide-border overflow-y-auto">
              {data.students.map((st) => (
                <li key={st.id}>
                  <button type="button" onClick={() => open({ type: 'student-attendance', groupId: group.id, student: { id: st.id, name: st.name } })}
                    className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-surface-hover">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-ink">{st.name}</span>
                      <span className="text-2xs text-ink-muted tabular-nums">
                        {st.attended}/{st.marked}{st.consecutive_absences >= 2 ? <span className="text-danger"> · {st.consecutive_absences} пропуска подряд</span> : null}
                      </span>
                    </span>
                    <span className="w-16 shrink-0"><Percent value={st.percent} className="block text-right text-sm font-medium" /><PercentBar value={st.percent} className="mt-1" /></span>
                    <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </div>
  )
}

export function GroupHomeworkTab({ group }: { group: GroupDetail }) {
  const { open } = useAssistantActions()
  const { filters, set, query } = useFilters()
  const { data, isPending, isError, refetch } = useGroupHomework(group.id, query)
  const s = data?.summary

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Всего ДЗ" value={s?.total ?? '—'} />
        <Kpi label="Выполнено" value={s?.complete ?? '—'} tone="text-brand-700" />
        <Kpi label="Есть пропуски" value={s?.missing ?? '—'} tone={s?.missing ? 'text-warning' : undefined} />
        <Kpi label="На проверке" value={s?.review ?? '—'} tone={s?.review ? 'text-info' : undefined} />
        <Kpi label="Средний % выполнения" value={<Percent value={s?.average_percent ?? null} />} />
      </div>

      <FiltersRow filters={filters} set={set}>
        <div className="w-full sm:w-44"><Select aria-label="Тренер" value={filters.teacher ? String(filters.teacher) : ''} placeholder="Все тренеры"
          onChange={(e) => set({ teacher: e.target.value ? Number(e.target.value) : undefined })} options={teacherOptions(group)} /></div>
        <div className="w-full sm:w-44"><Select aria-label="Статус ДЗ" value={filters.status ?? ''} placeholder="Все статусы"
          onChange={(e) => set({ status: e.target.value || undefined })}
          options={[{ value: 'open', label: 'Принимается' }, { value: 'review', label: 'На проверке' }, { value: 'complete', label: 'Завершено' }, { value: 'missing', label: 'Есть пропуски' }]} /></div>
      </FiltersRow>

      {isPending ? <LoadingState label="Загружаем ДЗ…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.homeworks.length === 0 ? <EmptyState icon={NotebookPen} title="Домашних заданий за период нет" /> : null}
      {data && data.homeworks.length > 0 ? (
        <section className="card overflow-hidden">
          <div className="max-h-[36rem] overflow-auto">
            <table className="w-full min-w-[680px] text-sm">
              <thead className="sticky top-0 z-10 bg-surface-muted text-left text-xs text-ink-secondary">
                <tr>
                  <th className="px-4 py-2 font-medium">№</th><th className="px-2 py-2 font-medium">ДЗ</th><th className="px-2 py-2 font-medium">Урок</th>
                  <th className="px-2 py-2 font-medium">Дедлайн</th><th className="px-2 py-2 font-medium">Выполнено</th><th className="px-4 py-2 font-medium">Статус</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.homeworks.map((hw) => (
                  <tr key={hw.id} onClick={() => open({ type: 'homework', homeworkId: hw.id })} className="cursor-pointer hover:bg-surface-hover">
                    <td className="px-4 py-2 text-ink-secondary tabular-nums">{hw.lesson.number}</td>
                    <td className="max-w-64 px-2 py-2"><span className="block truncate font-medium text-ink">{hw.title}</span>{hw.teacher ? <span className="block truncate text-xs text-ink-muted">{hw.teacher.name}</span> : null}</td>
                    <td className="px-2 py-2 whitespace-nowrap text-ink-secondary">Занятие {hw.lesson.number} · {day(hw.issued)}</td>
                    <td className="px-2 py-2 whitespace-nowrap text-ink-secondary">{hw.deadline ? day(hw.deadline) : '—'}</td>
                    <td className="w-32 px-2 py-2">
                      <span className="text-ink tabular-nums">{hw.done}/{hw.expected}</span>
                      <PercentBar value={hw.percent} className="mt-1" />
                    </td>
                    <td className="px-4 py-2"><HomeworkStateBadge status={hw.status} label={hw.status_display} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  )
}
