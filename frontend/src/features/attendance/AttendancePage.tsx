import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarCheck } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { lessonsApi } from '@/api/lessons'
import { AttendanceTable } from '@/components/academy/AttendanceTable'
import type { AttendanceRow } from '@/components/academy/AttendanceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useToast } from '@/components/ui/Toast'
import { useAttendanceRoster, useSaveAttendance } from '@/hooks/useAttendance'
import { useLesson } from '@/hooks/useLessons'
import { extractErrorMessage } from '@/lib/apiError'
import { resolveReturnTo } from '@/lib/returnTo'
import { todayISO } from '@/features/dashboard/useDashboardData'
import type { AttendanceStatus } from '@/types/attendance'
import { formatDate, formatTimeRange } from '@/utils/format'

/** No lesson (opened straight from the nav/dashboard, not from a Lesson
 * Detail page) has nowhere sensible to return to but the attendance list
 * itself. */
const ATTENDANCE_LIST_PATH = '/app/attendance'

export function AttendancePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const lessonParam = searchParams.get('lesson')
  const lessonId = lessonParam ? Number(lessonParam) : undefined
  // Never trust the raw query value — `resolveReturnTo` only ever hands back
  // this same-app path or the safe fallback, so a crafted link can't send a
  // teacher who just saved attendance off to an external site.
  const returnTo = resolveReturnTo(searchParams.get('returnTo'), ATTENDANCE_LIST_PATH)

  if (!lessonId) {
    return <LessonPicker onSelect={(id) => setSearchParams({ lesson: String(id) })} />
  }

  return <AttendanceEditor lessonId={lessonId} returnTo={returnTo} onChangeLesson={() => setSearchParams({})} />
}

function LessonPicker({ onSelect }: { onSelect: (lessonId: number) => void }) {
  const [date, setDate] = useState(todayISO());

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['attendance-picker', date],
    queryFn: () => lessonsApi.list({ date, ordering: 'start_time' }),
  })

  return (
    <div>
      <PageHeader title="Посещаемость" description="Выберите занятие, чтобы отметить студентов." />

      <div className="mb-5 max-w-xs">
        <DatePicker aria-label="Дата" value={date} onChange={(event) => setDate(event.target.value)} />
      </div>

      {isPending ? <LoadingState label="Ищем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={CalendarCheck} title="На эту дату занятий нет" description="Выберите другую дату." />
      ) : null}

      {data && data.results.length > 0 ? (
        <ul className="space-y-2">
          {data.results.map((lesson) => (
            <li key={lesson.id}>
              <button
                type="button"
                onClick={() => onSelect(lesson.id)}
                className="flex w-full items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-left hover:border-brand-200 hover:bg-brand-50/30"
              >
                <span>
                  <span className="block text-sm font-medium text-ink">
                    {formatTimeRange(lesson.start_time, lesson.end_time)} · {lesson.subject_name ?? 'Без предмета'}
                  </span>
                  <span className="block text-xs text-ink-secondary">{lesson.group_name}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function AttendanceEditor({
  lessonId,
  returnTo,
  onChangeLesson,
}: {
  lessonId: number
  returnTo: string
  onChangeLesson: () => void
}) {
  const { data: lesson } = useLesson(lessonId)
  const roster = useAttendanceRoster(lessonId)
  const saveMutation = useSaveAttendance(lessonId)
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [localStatus, setLocalStatus] = useState<Record<number, AttendanceStatus>>({})

  // Mirrors the backend's own enforcement (LessonSerializer.attendance_editable
  // / views._assert_lesson_editable) — never re-derived from the lesson
  // status here, so the two can't drift apart.
  const isReadOnly = lesson ? !lesson.attendance_editable : false

  useEffect(() => {
    if (!roster.data) return
    const initial: Record<number, AttendanceStatus> = {}
    for (const row of roster.data) {
      initial[row.student] = row.status ?? 'present'
    }
    setLocalStatus(initial)
  }, [roster.data])

  async function handleSave() {
    if (!roster.data) return
    const items = roster.data.map((row) => ({
      student: row.student,
      status: localStatus[row.student] ?? 'present',
    }))
    try {
      // One bulk upsert either way (see services.attendance_service on the
      // backend) — a first save creates every record, a later one updates
      // them, with no branching needed here for "create vs. update".
      await saveMutation.mutateAsync(items)
      showToast('Посещаемость успешно сохранена', 'success')
      // The mutation already invalidated this lesson's cached detail (see
      // useSaveAttendance), so landing back on it refetches fresh —
      // attendance_completed flips to true, the completion checklist and
      // the next suggested action ("Домашнее задание"/"Завершить занятие")
      // update on their own. `replace` drops the just-submitted attendance
      // form from history so Back doesn't return to a now-stale page.
      navigate(returnTo, { replace: true })
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сохранить посещаемость'), 'error')
    }
  }

  const rows: AttendanceRow[] = (roster.data ?? []).map((row) => ({
    studentId: row.student,
    studentName: row.student_name,
    status: localStatus[row.student] ?? row.status ?? 'present',
  }))

  return (
    <div>
      <PageHeader
        title="Посещаемость"
        description={lesson ? `${formatDate(lesson.date)} · ${formatTimeRange(lesson.start_time, lesson.end_time)} · ${lesson.group_name}` : undefined}
        actions={
          isReadOnly ? (
            <Badge tone="muted">Только просмотр</Badge>
          ) : (
            <Button variant="ghost" size="sm" onClick={onChangeLesson}>
              Выбрать другое занятие
            </Button>
          )
        }
      />

      {isReadOnly ? (
        <div className="mb-6 rounded-lg bg-surface-muted px-4 py-3 text-sm text-ink-secondary">
          Занятие завершено или отменено — посещаемость больше нельзя редактировать.
        </div>
      ) : null}

      {roster.isPending ? <LoadingState label="Загружаем список студентов…" /> : null}
      {roster.isError ? <ErrorState onRetry={() => void roster.refetch()} /> : null}

      {rows.length === 0 && roster.data ? <EmptyState title="В группе нет активных студентов" /> : null}

      {rows.length > 0 ? (
        <>
          <AttendanceTable
            rows={rows}
            onStatusChange={(studentId, status) => setLocalStatus((prev) => ({ ...prev, [studentId]: status }))}
            readOnly={isReadOnly}
          />
          {!isReadOnly ? (
            <div className="sticky bottom-20 mt-4 flex justify-end lg:bottom-4">
              <Button onClick={() => void handleSave()} isLoading={saveMutation.isPending} size="lg">
                Сохранить посещаемость
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
