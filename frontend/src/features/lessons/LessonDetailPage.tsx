import { useState } from 'react'
import { ExternalLink, FileText, Youtube } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { LESSON_STATUS_LABEL, LESSON_STATUS_TONE } from '@/components/academy/lessonStatus'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useAttendanceRoster } from '@/hooks/useAttendance'
import { useCreateHomework, useHomeworkList } from '@/hooks/useHomework'
import { useCancelLesson, useCompleteLesson, useLesson, useSetHomeworkNotRequired, useStartLesson } from '@/hooks/useLessons'
import { extractErrorMessage } from '@/lib/apiError'
import { attendanceUrlFor, homeworkUrlFor } from '@/lib/returnTo'
import { cn } from '@/utils/cn'
import { formatDate, formatTimeRange } from '@/utils/format'

import { LessonActionBar } from './LessonActionBar'
import type { LessonActionKey } from './lessonActions'
import { LessonProgressChecklist } from './LessonProgressChecklist'

export function LessonDetailPage() {
  const { id } = useParams<{ id: string }>()
  const lessonId = Number(id)
  const navigate = useNavigate()
  const { showToast } = useToast()

  const { data: lesson, isPending, isError, refetch } = useLesson(lessonId)
  const roster = useAttendanceRoster(lessonId)
  const homeworkList = useHomeworkList({ lesson: lessonId })

  const startMutation = useStartLesson()
  const completeMutation = useCompleteLesson()
  const cancelMutation = useCancelLesson()
  const homeworkNotRequiredMutation = useSetHomeworkNotRequired()

  const [isCancelModalOpen, setCancelModalOpen] = useState(false)
  const [isHomeworkModalOpen, setHomeworkModalOpen] = useState(false)
  const [pendingKey, setPendingKey] = useState<LessonActionKey | null>(null)

  if (isPending) return <LoadingState label="Загружаем занятие…" />
  if (isError || !lesson) return <ErrorState onRetry={() => void refetch()} />

  const homework = homeworkList.data?.results[0]
  const isReadOnly = lesson.status === 'completed' || lesson.status === 'cancelled'
  const missingLabels = lesson.completion_requirements.filter((r) => !r.satisfied).map((r) => r.label)

  function goToHomework() {
    if (homework) navigate(homeworkUrlFor(homework.id, `/app/lessons/${lesson.id}`))
  }

  async function handleAction(key: LessonActionKey) {
    switch (key) {
      case 'start': {
        setPendingKey('start')
        try {
          await startMutation.mutateAsync(lesson!.id)
          showToast('Занятие начато', 'success')
        } catch (error) {
          showToast(extractErrorMessage(error, 'Не удалось начать занятие'), 'error')
        } finally {
          setPendingKey(null)
        }
        return
      }
      case 'complete': {
        setPendingKey('complete')
        try {
          await completeMutation.mutateAsync(lesson!.id)
          showToast('Занятие завершено', 'success')
        } catch (error) {
          showToast(extractErrorMessage(error, 'Не удалось завершить занятие'), 'error')
        } finally {
          setPendingKey(null)
        }
        return
      }
      case 'cancel':
        setCancelModalOpen(true)
        return
      case 'attendance':
      case 'view_attendance':
        navigate(attendanceUrlFor(lesson.id, `/app/lessons/${lesson.id}`))
        return
      case 'homework':
        if (homework) goToHomework()
        else setHomeworkModalOpen(true)
        return
      case 'view_homework':
      case 'view_results':
        goToHomework()
        return
      case 'view_details':
        // Never reached on the detail page itself — only meaningful on a
        // lesson card/list row, where it navigates here.
        return
    }
  }

  async function handleMarkHomeworkNotRequired() {
    try {
      await homeworkNotRequiredMutation.mutateAsync({ id: lesson.id, value: true })
      showToast('Отмечено: ДЗ не требуется', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось изменить отметку'), 'error')
    }
  }

  return (
    <div>
      <PageHeader
        title={formatTimeRange(lesson.start_time, lesson.end_time)}
        description={`${formatDate(lesson.date)} · ${lesson.subject_name ?? 'Без предмета'}${lesson.topic ? ` — ${lesson.topic}` : ''}`}
        actions={<Badge tone={LESSON_STATUS_TONE[lesson.status]}>{LESSON_STATUS_LABEL[lesson.status]}</Badge>}
      />

      {lesson.status === 'cancelled' ? (
        <div className="mb-6 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger">
          Занятие отменено{lesson.cancellation_reason ? `. Причина: ${lesson.cancellation_reason}` : '.'}
        </div>
      ) : null}

      {lesson.status === 'completed' ? (
        <div className="mb-6 rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700">
          Занятие завершено{lesson.completed_by_name ? ` — ${lesson.completed_by_name}` : ''}
          {lesson.completed_at ? ` · ${formatDate(lesson.completed_at)}` : ''}. Доступно только для просмотра.
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="mb-3 text-sm font-medium text-ink-secondary">О занятии</p>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-ink-secondary">Группа</dt>
                <dd className="mt-0.5">
                  <Link to={`/app/groups/${lesson.group}`} className="font-medium text-brand-700 hover:underline">
                    {lesson.group_name}
                  </Link>
                </dd>
              </div>
              <div>
                <dt className="text-ink-secondary">Аудитория</dt>
                <dd className="mt-0.5 font-medium text-ink">{lesson.room_name ?? '—'}</dd>
              </div>
            </dl>
            {lesson.description ? <p className="mt-4 text-sm text-ink">{lesson.description}</p> : null}
          </div>

          {(lesson.youtube_url || lesson.presentation_urls.length > 0) ? (
            <div className="rounded-xl border border-border bg-surface p-5">
              <p className="mb-3 text-sm font-medium text-ink-secondary">Материалы</p>
              <ul className="space-y-2">
                {lesson.youtube_url ? (
                  <li>
                    <a
                      href={lesson.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 text-sm text-brand-700 hover:underline"
                    >
                      <Youtube className="size-4" aria-hidden />
                      YouTube
                      <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </li>
                ) : null}
                {lesson.presentation_urls.map((url, index) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-brand-700 hover:underline">
                      <FileText className="size-4" aria-hidden />
                      Презентация {lesson.presentation_urls.length > 1 ? index + 1 : ''}
                      <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {lesson.status !== 'scheduled' ? (
            <AttendanceStatsCard roster={roster.data} isPending={roster.isPending} />
          ) : null}
        </div>

        <div className="space-y-4">
          <div
            className={cn(
              'rounded-xl border p-5',
              isReadOnly ? 'border-dashed border-border bg-surface-muted' : 'border-border bg-surface',
            )}
          >
            <p className="mb-3 text-sm font-medium text-ink-secondary">{isReadOnly ? 'Просмотр' : 'Действия'}</p>

            <LessonActionBar lesson={lesson} onAction={(key) => void handleAction(key)} pendingKey={pendingKey} />

            {lesson.status === 'in_progress' ? (
              <div className="mt-4 border-t border-border pt-4">
                <LessonProgressChecklist
                  lesson={lesson}
                  onMarkHomeworkNotRequired={() => void handleMarkHomeworkNotRequired()}
                  isMarkingHomeworkNotRequired={homeworkNotRequiredMutation.isPending}
                />
                {!lesson.can_complete && missingLabels.length > 0 ? (
                  <div className="mt-3 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
                    Нельзя завершить занятие: {missingLabels.join('; ')}.
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {homework ? (
            <div className="rounded-xl border border-border bg-surface p-5">
              <p className="mb-2 text-sm font-medium text-ink-secondary">Домашнее задание</p>
              <p className="font-medium text-ink">{homework.title}</p>
              {homework.deadline ? <p className="mt-1 text-sm text-ink-secondary">Срок: {formatDate(homework.deadline)}</p> : null}
              <p className="mt-2 text-sm text-ink-secondary">{homework.results_count} результатов</p>
            </div>
          ) : null}
        </div>
      </div>

      <CancelLessonModal lessonId={lesson.id} isOpen={isCancelModalOpen} onClose={() => setCancelModalOpen(false)} mutation={cancelMutation} />
      <AddHomeworkModal lessonId={lesson.id} isOpen={isHomeworkModalOpen} onClose={() => setHomeworkModalOpen(false)} />
    </div>
  )
}

function AttendanceStatsCard({
  roster,
  isPending,
}: {
  roster: { status: string | null }[] | undefined
  isPending: boolean
}) {
  const present = roster?.filter((row) => row.status === 'present').length ?? 0
  const absent = roster?.filter((row) => row.status === 'absent').length ?? 0
  const late = roster?.filter((row) => row.status === 'late').length ?? 0
  const excused = roster?.filter((row) => row.status === 'excused').length ?? 0
  const totalStudents = roster?.length ?? 0

  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-ink-secondary">Посещаемость</p>
        <span className="text-sm text-ink-secondary">{totalStudents} студентов</span>
      </div>
      {isPending ? (
        <LoadingState label="Загружаем…" />
      ) : (
        <div className="grid grid-cols-4 gap-2 text-center">
          <StatBlock label="Present" value={present} tone="success" />
          <StatBlock label="Absent" value={absent} tone="danger" />
          <StatBlock label="Late" value={late} tone="warning" />
          <StatBlock label="Excused" value={excused} tone="muted" />
        </div>
      )}
    </div>
  )
}

function StatBlock({ label, value, tone }: { label: string; value: number; tone: BadgeTone }) {
  const TONE_TEXT: Record<BadgeTone, string> = {
    success: 'text-brand-700',
    danger: 'text-danger',
    warning: 'text-warning',
    muted: 'text-ink-muted',
    brand: 'text-brand-700',
  }
  return (
    <div className="rounded-lg bg-surface-muted p-3">
      <p className={`text-xl font-semibold ${TONE_TEXT[tone]}`}>{value}</p>
      <p className="text-xs text-ink-secondary">{label}</p>
    </div>
  )
}

function CancelLessonModal({
  lessonId,
  isOpen,
  onClose,
  mutation,
}: {
  lessonId: number
  isOpen: boolean
  onClose: () => void
  mutation: ReturnType<typeof useCancelLesson>
}) {
  const [reason, setReason] = useState('')
  const { showToast } = useToast()

  async function handleConfirm() {
    try {
      await mutation.mutateAsync({ id: lessonId, reason })
      showToast('Занятие отменено', 'success')
      setReason('')
      onClose()
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось отменить занятие'), 'error')
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Отменить занятие">
      <p className="text-sm text-ink-secondary">Укажите причину отмены (необязательно).</p>
      <textarea
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        rows={3}
        maxLength={255}
        placeholder="Например: тренер заболел"
        className="mt-3 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink focus-visible:border-brand-500"
      />
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
          Не отменять
        </Button>
        <Button variant="danger" onClick={() => void handleConfirm()} isLoading={mutation.isPending}>
          Отменить занятие
        </Button>
      </div>
    </Modal>
  )
}

function AddHomeworkModal({ lessonId, isOpen, onClose }: { lessonId: number; isOpen: boolean; onClose: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [deadline, setDeadline] = useState('')
  const createMutation = useCreateHomework()
  const { showToast } = useToast()

  async function handleSubmit() {
    if (!title.trim()) return
    try {
      await createMutation.mutateAsync({ lesson: lessonId, title: title.trim(), description, deadline: deadline || null })
      showToast('Домашнее задание добавлено', 'success')
      setTitle('')
      setDescription('')
      setDeadline('')
      onClose()
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось добавить домашнее задание'), 'error')
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Добавить домашнее задание">
      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-ink-secondary" htmlFor="homework-title">
            Название
          </label>
          <input
            id="homework-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-ink focus-visible:border-brand-500"
            placeholder="Например: Собрать простого робота"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink-secondary" htmlFor="homework-description">
            Описание
          </label>
          <textarea
            id="homework-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink focus-visible:border-brand-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink-secondary" htmlFor="homework-deadline">
            Срок сдачи
          </label>
          <input
            id="homework-deadline"
            type="date"
            value={deadline}
            onChange={(event) => setDeadline(event.target.value)}
            className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-ink focus-visible:border-brand-500"
          />
        </div>
      </div>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={createMutation.isPending}>
          Отмена
        </Button>
        <Button onClick={() => void handleSubmit()} isLoading={createMutation.isPending} disabled={!title.trim()}>
          Добавить
        </Button>
      </div>
    </Modal>
  )
}
