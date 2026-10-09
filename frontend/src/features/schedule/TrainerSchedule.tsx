import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { addDays, addWeeks, endOfWeek, format, isToday, startOfWeek } from 'date-fns'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'

import { lessonsApi, type LessonListParams } from '@/api/lessons'
import { roomsApi } from '@/api/rooms'
import { subjectsApi } from '@/api/subjects'
import { RoomAvailabilityPanel } from '@/components/academy/RoomAvailabilityPanel'
import { LESSON_STATUS_OPTIONS } from '@/components/academy/lessonStatus'
import { DaySchedule } from '@/components/calendar/DaySchedule'
import { WeekCalendar } from '@/components/calendar/WeekCalendar'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useGroups } from '@/hooks/useGroups'
import { fetchAllPages } from '@/lib/fetchAllPages'
import type { Lesson, LessonStatus } from '@/types/academy'
import { formatDate, formatDateShort } from '@/utils/format'

type ViewMode = 'week' | 'day'

export function TrainerSchedule() {
  const [anchor, setAnchor] = useState(() => new Date())
  const [view, setView] = useState<ViewMode>('week')
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [roomId, setRoomId] = useState('')
  const [status, setStatus] = useState('')
  const [showRoomAvailability, setShowRoomAvailability] = useState(false)

  const rangeStart = view === 'week' ? startOfWeek(anchor, { weekStartsOn: 1 }) : anchor
  const rangeEnd = view === 'week' ? endOfWeek(anchor, { weekStartsOn: 1 }) : anchor
  const dateFrom = format(rangeStart, 'yyyy-MM-dd')
  const dateTo = format(rangeEnd, 'yyyy-MM-dd')

  const { data: groupsData } = useGroups({})
  const { data: subjectsData } = useQuery({ queryKey: ['subjects', 'list'], queryFn: () => subjectsApi.list({ is_active: true }) })
  const { data: roomsData } = useQuery({ queryKey: ['rooms', 'list'], queryFn: () => roomsApi.list({ is_active: true }) })

  const filters: LessonListParams = {
    date_from: dateFrom,
    date_to: dateTo,
    ordering: 'date,start_time',
    ...(groupId ? { group: Number(groupId) } : {}),
    ...(subjectId ? { subject: Number(subjectId) } : {}),
    ...(roomId ? { room: Number(roomId) } : {}),
    ...(status ? { status: status as LessonStatus } : {}),
  }

  const {
    data: lessons,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['schedule', filters],
    queryFn: () => fetchAllPages<Lesson>((page) => lessonsApi.list({ ...filters, page })),
  })

  const dayCount = view === 'week' ? 7 : 1
  const days = Array.from({ length: dayCount }, (_, index) => {
    const date = format(addDays(rangeStart, index), 'yyyy-MM-dd')
    return {
      date,
      isToday: isToday(addDays(rangeStart, index)),
      lessons: (lessons ?? []).filter((lesson) => lesson.date === date),
    }
  })

  function goToStep(direction: -1 | 1) {
    setAnchor((current) => (view === 'week' ? addWeeks(current, direction) : addDays(current, direction)))
  }

  return (
    <div>
      <PageHeader title="Расписание" description="Ваши занятия по дням и неделям." />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={() => goToStep(-1)} aria-label="Предыдущий период" className="w-10 px-0">
            <ChevronLeft className="size-4" aria-hidden />
          </Button>
          <Button variant="secondary" onClick={() => setAnchor(new Date())}>
            Сегодня
          </Button>
          <Button variant="secondary" onClick={() => goToStep(1)} aria-label="Следующий период" className="w-10 px-0">
            <ChevronRight className="size-4" aria-hidden />
          </Button>
          <span className="w-full text-sm font-medium text-ink-secondary min-[400px]:ml-1 min-[400px]:w-auto">
            {dateFrom === dateTo ? formatDate(dateFrom) : `${formatDateShort(dateFrom)} — ${formatDateShort(dateTo)}`}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl<ViewMode>
            aria-label="Вид расписания"
            value={view}
            onChange={setView}
            options={[
              { value: 'week', label: 'Неделя' },
              { value: 'day', label: 'День' },
            ]}
          />
          <Button
            variant={showRoomAvailability ? 'primary' : 'secondary'}
            leftIcon={<Search className="size-4" aria-hidden />}
            onClick={() => setShowRoomAvailability((value) => !value)}
          >
            Свободные аудитории
          </Button>
        </div>
      </div>

      {showRoomAvailability ? (
        <div className="mb-6">
          <RoomAvailabilityPanel defaultDate={dateFrom} />
        </div>
      ) : null}

      <div className="mb-6 grid grid-cols-1 gap-3 min-[400px]:grid-cols-2 lg:grid-cols-4">
        <Select
          aria-label="Группа"
          placeholder="Все группы"
          value={groupId}
          onChange={(event) => setGroupId(event.target.value)}
          options={(groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
        />
        <Select
          aria-label="Предмет"
          placeholder="Все предметы"
          value={subjectId}
          onChange={(event) => setSubjectId(event.target.value)}
          options={(subjectsData?.results ?? []).map((subject) => ({ value: String(subject.id), label: subject.name }))}
        />
        <Select
          aria-label="Аудитория"
          placeholder="Все аудитории"
          value={roomId}
          onChange={(event) => setRoomId(event.target.value)}
          options={(roomsData?.results ?? []).map((room) => ({ value: String(room.id), label: room.name }))}
        />
        <Select
          aria-label="Статус"
          placeholder="Все статусы"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          options={LESSON_STATUS_OPTIONS}
        />
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {lessons && !isPending ? (
        view === 'week' ? (
          <WeekCalendar days={days} />
        ) : (
          <DaySchedule date={dateFrom} lessons={days[0]?.lessons ?? []} />
        )
      ) : null}
    </div>
  )
}
