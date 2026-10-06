import { Fragment, useState } from 'react'
import type { ReactNode } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { BookOpen, ChevronRight, ClipboardCheck, Eye, GraduationCap, NotebookPen, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useControlStudent, useGroupAttendance, useHomeworkDetail, useLessonDetail } from '@/hooks/useAssistant'
import type { ControlPeriod, Ref } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { AttendanceBadge, ControlStatusBadge, HomeworkStateBadge, Percent, PercentBar, SubmissionBadge } from './badges'

/**
 * Read-only detail views of the Assistant's records: a lesson (marks +
 * its homework), a homework (every student's result), one student's
 * attendance in a group, one student's activity profile. Nothing here can
 * change a record — only open the next detail.
 */

const day = (value: string) => format(parseISO(value), 'd MMM', { locale: ru })
const dayLong = (value: string) => format(parseISO(value), 'd MMMM', { locale: ru })
const time = (value: string | null) => (value ? format(parseISO(value), 'dd.MM HH:mm') : '—')

function ReadOnlyNote() {
  return (
    <p className="mt-4 flex items-center gap-1.5 text-xs text-ink-muted">
      <Eye className="size-3.5" aria-hidden />Только просмотр — данные ведёт тренер.
    </p>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2">
      <p className="text-2xs text-ink-secondary">{label}</p>
      <p className="truncate text-sm font-semibold text-ink tabular-nums">{value}</p>
    </div>
  )
}

export function LessonDetailModal({ lessonId, onClose, onOpenHomework }: { lessonId: number; onClose: () => void; onOpenHomework: (id: number) => void }) {
  const { data, isPending, isError, refetch } = useLessonDetail(lessonId)
  return (
    <Modal isOpen onClose={onClose} size="lg" icon={<BookOpen className="size-5 text-brand-600" aria-hidden />}
      title={data ? `${dayLong(data.date)} · Занятие ${data.lesson_number}` : 'Занятие'}>
      {isPending ? <LoadingState label="Загружаем…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <div>
            <p className="font-medium text-ink">{data.topic || data.subject?.name || '—'}</p>
            <p className="text-sm text-ink-secondary">{data.group.name} · {data.start}–{data.end} · Тренер: {data.teacher?.name ?? '—'} · {data.status_display}</p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Присутствовали" value={`${data.attendance.attended}/${data.attendance.total}`} />
            <Stat label="Отмечено" value={`${data.attendance.marked}/${data.attendance.total}`} />
            <Stat label="Посещаемость" value={<Percent value={data.attendance.percent} />} />
          </div>

          {data.homeworks.length ? (
            <section>
              <h3 className="mb-1.5 text-sm font-semibold text-ink">Домашнее задание</h3>
              <ul className="space-y-1.5">
                {data.homeworks.map((hw) => (
                  <li key={hw.id}>
                    <button type="button" onClick={() => onOpenHomework(hw.id)}
                      className="flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2 text-left hover:border-brand-200 hover:bg-brand-50/40">
                      <NotebookPen className="size-4 shrink-0 text-brand-600" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">«{hw.title}»</span>
                        <span className="text-xs text-ink-secondary tabular-nums">{hw.done}/{hw.expected} выполнено{hw.deadline ? ` · срок ${day(hw.deadline)}` : ''}</span>
                      </span>
                      <HomeworkStateBadge status={hw.status} label={hw.status_display} />
                      <span className="hidden items-center text-sm font-medium text-brand-700 sm:flex">Открыть ДЗ<ChevronRight className="size-4" aria-hidden /></span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : <p className="text-sm text-ink-secondary">Домашнего задания к занятию нет.</p>}

          <section>
            <h3 className="mb-1.5 text-sm font-semibold text-ink">Посещаемость</h3>
            <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface-muted text-left text-xs text-ink-secondary">
                  <tr><th className="px-3 py-1.5 font-medium">Студент</th><th className="px-3 py-1.5 font-medium">Статус</th></tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.records.map((r) => (
                    <tr key={r.student.id}>
                      <td className="px-3 py-1.5 text-ink">{r.student.name}{r.comment ? <span className="block text-xs text-ink-muted">{r.comment}</span> : null}</td>
                      <td className="px-3 py-1.5"><AttendanceBadge status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <ReadOnlyNote />
        </div>
      ) : null}
    </Modal>
  )
}

export function HomeworkDetailModal({ homeworkId, onClose, onOpenLesson }: { homeworkId: number; onClose: () => void; onOpenLesson: (id: number) => void }) {
  const { data, isPending, isError, refetch } = useHomeworkDetail(homeworkId)
  const [opened, setOpened] = useState<number | null>(null)
  return (
    <Modal isOpen onClose={onClose} size="lg" icon={<NotebookPen className="size-5 text-brand-600" aria-hidden />}
      title={data ? `ДЗ к занятию ${data.lesson.number}` : 'Домашнее задание'}>
      {isPending ? <LoadingState label="Загружаем…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-semibold text-ink">{data.title}</p>
              {data.description ? <p className="mt-0.5 text-sm whitespace-pre-line text-ink-secondary">{data.description}</p> : null}
            </div>
            <HomeworkStateBadge status={data.status} label={data.status_display} />
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-ink-secondary">Урок</dt>
              <dd><button type="button" onClick={() => onOpenLesson(data.lesson.id)} className="font-medium text-brand-700 hover:underline">Занятие {data.lesson.number}</button></dd></div>
            <div><dt className="text-xs text-ink-secondary">Тренер</dt><dd className="truncate font-medium text-ink">{data.teacher?.name ?? '—'}</dd></div>
            <div><dt className="text-xs text-ink-secondary">Выдано</dt><dd className="font-medium text-ink">{dayLong(data.issued)}</dd></div>
            <div><dt className="text-xs text-ink-secondary">Дедлайн</dt><dd className="font-medium text-ink">{data.deadline ? dayLong(data.deadline) : 'без срока'}</dd></div>
          </dl>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Выполнили" value={`${data.done}/${data.expected}`} />
            <Stat label="Не выполнили" value={data.due ? `${data.not_done}/${data.expected}` : 'срок не наступил'} />
            <Stat label="На проверке" value={data.pending} />
          </div>
          <div className="max-h-80 overflow-y-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-muted text-left text-xs text-ink-secondary">
                <tr><th className="px-3 py-1.5 font-medium">Студент</th><th className="px-3 py-1.5 font-medium">Статус</th><th className="px-3 py-1.5 font-medium">Отправлено</th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.students.map((row) => (
                  <Fragment key={row.student.id}>
                    <tr className={cn(row.submitted_at || row.score !== null || row.comment ? 'cursor-pointer hover:bg-surface-hover' : '')}
                      onClick={() => setOpened(opened === row.student.id ? null : row.student.id)}>
                      <td className="px-3 py-1.5 text-ink">{row.student.name}</td>
                      <td className="px-3 py-1.5"><SubmissionBadge state={row.state} label={row.status_display} /></td>
                      <td className="px-3 py-1.5 text-ink-secondary tabular-nums">{time(row.submitted_at)}</td>
                    </tr>
                    {opened === row.student.id ? (
                      <tr className="bg-surface-muted/60">
                        <td colSpan={3} className="px-3 py-2 text-xs text-ink-secondary">
                          Сдано: {time(row.submitted_at)} · Проверено: {time(row.checked_at)} · Оценка: {row.score ?? '—'}
                          {row.comment ? <span className="mt-0.5 block text-ink">Комментарий тренера: {row.comment}</span> : null}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <ReadOnlyNote />
        </div>
      ) : null}
    </Modal>
  )
}

export function StudentAttendanceModal({ groupId, student, onClose, onOpenLesson }: { groupId: number; student: Ref; onClose: () => void; onOpenLesson: (id: number) => void }) {
  const { data, isPending } = useGroupAttendance(groupId, { student: student.id, period: 'all' })
  const s = data?.summary
  return (
    <Modal isOpen onClose={onClose} title={student.name} icon={<GraduationCap className="size-5 text-brand-600" aria-hidden />}>
      {isPending || !data || !s ? <LoadingState label="Загружаем…" /> : (
        <div className="space-y-4">
          <div>
            <p className="text-sm text-ink-secondary">Посещаемость в группе</p>
            <p className="text-2xl font-semibold text-ink"><Percent value={s.percent} /></p>
            <PercentBar value={s.percent} className="mt-1.5" />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Посещения" value={s.attended} />
            <Stat label="Пропуски" value={s.absent} />
            <Stat label="Опоздания" value={s.late} />
          </div>
          <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-muted text-left text-xs text-ink-secondary">
                <tr><th className="px-3 py-1.5 font-medium">Дата</th><th className="px-3 py-1.5 font-medium">Занятие</th><th className="px-3 py-1.5 font-medium">Статус</th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.lessons.map((l) => (
                  <tr key={l.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => onOpenLesson(l.id)}>
                    <td className="px-3 py-1.5 whitespace-nowrap text-ink">{day(l.date)}</td>
                    <td className="px-3 py-1.5 text-ink-secondary">Занятие {l.lesson_number}</td>
                    <td className="px-3 py-1.5"><AttendanceBadge status={l.student_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link to={`/assistant/students/${student.id}`} onClick={onClose} className="inline-flex items-center text-sm font-medium text-brand-700 hover:underline">
            Профиль студента <ChevronRight className="size-4" aria-hidden />
          </Link>
          <ReadOnlyNote />
        </div>
      )}
    </Modal>
  )
}

const PERIODS: { value: ControlPeriod; label: string }[] = [
  { value: '7d', label: '7 дн.' }, { value: '14d', label: '14 дн.' }, { value: '30d', label: '30 дн.' },
  { value: 'month', label: 'Месяц' }, { value: 'all', label: 'Всё' },
]

export function ControlStudentModal({ studentId, period: initial, onClose }: { studentId: number; period: ControlPeriod; onClose: () => void }) {
  const [period, setPeriod] = useState<ControlPeriod>(initial)
  const { data, isPending } = useControlStudent(studentId, period)
  const a = data?.activity
  return (
    <Modal isOpen onClose={onClose} size="lg" icon={<ShieldAlert className="size-5 text-brand-600" aria-hidden />} title={data?.student.name ?? 'Студент'}>
      {isPending || !data ? <LoadingState label="Загружаем…" /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-ink-secondary">Общий статус:</span>
              {a ? <ControlStatusBadge status={a.status} label={a.status_label} /> : null}
              {a?.group ? <span className="text-ink-secondary">· {a.group.name}</span> : null}
            </div>
            <SegmentedControl aria-label="Период" options={PERIODS} value={period} onChange={setPeriod} />
          </div>
          {data.note ? <p className="rounded-lg bg-info-soft px-3 py-2 text-sm text-info">{data.note}</p> : null}
          {a ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <section className="rounded-lg border border-border p-3">
                  <div className="flex items-baseline justify-between"><h3 className="text-sm font-semibold text-ink">Посещаемость</h3><Percent value={a.attendance} className="text-lg font-semibold" /></div>
                  <PercentBar value={a.attendance} className="mt-1.5" />
                  <dl className="mt-2 grid grid-cols-3 gap-1 text-xs">
                    <div><dt className="text-ink-secondary">Посетил</dt><dd className="font-semibold text-ink">{a.attended}</dd></div>
                    <div><dt className="text-ink-secondary">Пропустил</dt><dd className="font-semibold text-ink">{a.absent}</dd></div>
                    <div><dt className="text-ink-secondary">Подряд</dt><dd className={cn('font-semibold', a.consecutive_absences >= 3 ? 'text-danger' : 'text-ink')}>{a.consecutive_absences}</dd></div>
                  </dl>
                </section>
                <section className="rounded-lg border border-border p-3">
                  <div className="flex items-baseline justify-between"><h3 className="text-sm font-semibold text-ink">Домашние задания</h3><Percent value={a.homework} className="text-lg font-semibold" /></div>
                  <PercentBar value={a.homework} className="mt-1.5" />
                  <dl className="mt-2 grid grid-cols-3 gap-1 text-xs">
                    <div><dt className="text-ink-secondary">Выполнено</dt><dd className="font-semibold text-ink">{a.homework_done}</dd></div>
                    <div><dt className="text-ink-secondary">Не выполнено</dt><dd className="font-semibold text-ink">{a.homework_missed}</dd></div>
                    <div><dt className="text-ink-secondary">Подряд</dt><dd className={cn('font-semibold', a.consecutive_missed_homework >= 3 ? 'text-danger' : 'text-ink')}>{a.consecutive_missed_homework}</dd></div>
                  </dl>
                </section>
              </div>
              <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
                <Stat label="Последний урок" value={a.last_attended ? dayLong(a.last_attended) : '—'} />
                <Stat label="Последнее ДЗ" value={a.last_homework_done ? dayLong(a.last_homework_done) : '—'} />
                <Stat label="Последняя активность" value={a.last_activity ? dayLong(a.last_activity) : '—'} />
              </dl>
              <section>
                <h3 className="mb-1.5 text-sm font-semibold text-ink">Активность</h3>
                {data.timeline.length === 0 ? <p className="text-sm text-ink-secondary">За период событий нет.</p> : (
                  <ol className="max-h-64 space-y-1 overflow-y-auto">
                    {data.timeline.map((e, i) => (
                      <li key={i} className="flex items-center gap-3 text-sm">
                        <span className="w-14 shrink-0 text-xs text-ink-muted tabular-nums">{day(e.date)}</span>
                        <span className={cn('flex size-5 shrink-0 items-center justify-center rounded-full text-2xs font-bold',
                          e.neutral ? 'bg-info-soft text-info' : e.ok ? 'bg-brand-50 text-brand-700' : 'bg-danger-soft text-danger')} aria-hidden>
                          {e.kind === 'homework' ? <NotebookPen className="size-3" /> : <ClipboardCheck className="size-3" />}
                        </span>
                        <span className={cn('shrink-0 font-medium', e.neutral ? 'text-info' : e.ok ? 'text-ink' : 'text-danger')}>{e.text}</span>
                        <span className="min-w-0 truncate text-xs text-ink-secondary">{e.detail}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </>
          ) : null}
          <Link to={`/assistant/students/${studentId}`} onClick={onClose} className="inline-flex items-center text-sm font-medium text-brand-700 hover:underline">
            Профиль студента <ChevronRight className="size-4" aria-hidden />
          </Link>
          <ReadOnlyNote />
        </div>
      )}
    </Modal>
  )
}
