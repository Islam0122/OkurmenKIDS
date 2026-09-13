import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, CalendarX2, CheckCircle2, ChevronLeft, ChevronRight, ListChecks } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { groupsApi } from '@/api/groups'
import { lessonsApi } from '@/api/lessons'
import { subjectsApi } from '@/api/subjects'
import { LessonCard } from '@/components/academy/LessonCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useLessons } from '@/hooks/useLessons'
import { fetchAllPages } from '@/lib/fetchAllPages'
import type { Group, Lesson, LessonStatus } from '@/types/academy'
import { cn } from '@/utils/cn'
import { formatDate, formatTimeRange } from '@/utils/format'

import { LessonDayCard } from './LessonDayCard'
import {
  DEFAULT_LESSON_VIEW,
  LESSON_VIEW_TABS,
  addDaysISO,
  dateSectionHeading,
  dateSectionLabel,
  groupLessonsByDate,
  hasLessonPassed,
  isLessonView,
  nextWeekRange,
  thisWeekRange,
  todayISO,
  tomorrowISO,
  upcomingWindow,
} from './lessonViews'
import type { DateRange, LessonView } from './lessonViews'
import { useLessonEnrichment } from './useLessonEnrichment'
import { OPERATIONAL_STATUS_LABELS, useLessonOperationalStatus } from './useLessonOperationalStatus'
import type { LessonOperationalStatus } from './useLessonOperationalStatus'

const STATUS_OPTIONS: { value: LessonStatus; label: string }[] = [
  { value: 'planned', label: 'Запланировано' },
  { value: 'completed', label: 'Проведено' },
  { value: 'cancelled', label: 'Отменено' },
]

export function LessonsListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawView = searchParams.get('view')
  const view: LessonView = isLessonView(rawView) ? rawView : DEFAULT_LESSON_VIEW

  // Every group this teacher has, fetched once and shared by every tab —
  // for the "N студентов" hint and the group filter dropdowns. Bounded to a
  // teacher's own groups (never all academy groups), so fetching all pages
  // stays well within `fetchAllPages`'s "small per-teacher dataset" contract.
  const { data: groupsData } = useQuery({
    queryKey: ['groups', 'all-for-teacher'],
    queryFn: () => fetchAllPages<Group>((page) => groupsApi.list({ page })),
  })
  const groupStudentsCount = useMemo(() => {
    const map = new Map<number, number>()
    for (const group of groupsData ?? []) map.set(group.id, group.students_count)
    return map
  }, [groupsData])

  function selectView(nextView: LessonView) {
    setSearchParams(nextView === DEFAULT_LESSON_VIEW ? {} : { view: nextView })
  }

  return (
    <div>
      <PageHeader title="Мои занятия" description="Все ваши запланированные и проведённые уроки." />

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-border" role="tablist" aria-label="Период">
        {LESSON_VIEW_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={view === tab.key}
            onClick={() => selectView(tab.key)}
            className={cn(
              'shrink-0 border-b-2 px-3 py-2.5 text-sm font-medium',
              view === tab.key ? 'border-brand-500 text-brand-700' : 'border-transparent text-ink-secondary hover:text-ink',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {view === 'today' ? <DayLessonsView mode="today" groupStudentsCount={groupStudentsCount} /> : null}
      {view === 'tomorrow' ? <DayLessonsView mode="tomorrow" groupStudentsCount={groupStudentsCount} /> : null}
      {view === 'week' ? <GroupedRangeView range={thisWeekRange()} emptyTitle="На этой неделе занятий нет" /> : null}
      {view === 'next_week' ? <GroupedRangeView range={nextWeekRange()} emptyTitle="На следующей неделе занятий нет" /> : null}
      {view === 'upcoming' ? <GroupedRangeView range={upcomingWindow()} emptyTitle="Предстоящих занятий нет" excludePast /> : null}
      {view === 'all' ? <AllLessonsView groupsData={groupsData} /> : null}
      {view === 'completed' ? <CompletedLessonsView groupsData={groupsData} /> : null}
      {view === 'cancelled' ? <CancelledLessonsView groupsData={groupsData} /> : null}
    </div>
  )
}

/** Powers both the "Сегодня" and "Завтра" tabs — the only real difference is
 * which single date is shown; the day-navigation arrows only make sense on
 * "Сегодня" (where the date can drift away from today). */
function DayLessonsView({ mode, groupStudentsCount }: { mode: 'today' | 'tomorrow'; groupStudentsCount: Map<number, number> }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const isTodayMode = mode === 'today'
  const date = isTodayMode ? (searchParams.get('date') ?? todayISO()) : tomorrowISO()

  const { data, isPending, isError, refetch } = useLessons({ date, ordering: 'start_time' })
  const lessons = data?.results ?? []

  const idsNeedingStatus = lessons
    .filter((lesson) => lesson.status !== 'cancelled' && hasLessonPassed(lesson))
    .map((lesson) => lesson.id)
  const enrichment = useLessonEnrichment(idsNeedingStatus)

  function goToDate(nextDate: string) {
    const next = new URLSearchParams(searchParams)
    next.set('view', 'today')
    next.set('date', nextDate)
    setSearchParams(next)
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">{dateSectionLabel(date)}</h2>
          <p className="text-sm text-ink-secondary">{formatDate(date)}</p>
        </div>
        {isTodayMode ? (
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => goToDate(addDaysISO(date, -1))} aria-label="Предыдущий день">
              <ChevronLeft className="size-4" aria-hidden />
            </Button>
            <Button variant="secondary" size="sm" onClick={() => goToDate(todayISO())}>
              Сегодня
            </Button>
            <Button variant="secondary" size="sm" onClick={() => goToDate(addDaysISO(date, 1))} aria-label="Следующий день">
              <ChevronRight className="size-4" aria-hidden />
            </Button>
          </div>
        ) : null}
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && lessons.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title={emptyTitleFor(mode, date)}
          description={isTodayMode && date === todayISO() ? 'У вас нет запланированных уроков на сегодня.' : undefined}
          action={
            isTodayMode && date === todayISO() ? (
              <Link to="/app/lessons?view=tomorrow">
                <Button variant="secondary" size="sm">
                  Посмотреть завтрашние занятия
                </Button>
              </Link>
            ) : undefined
          }
        />
      ) : null}

      {lessons.length > 0 ? (
        <div className="space-y-3">
          {lessons.map((lesson) => {
            const status = enrichment.get(lesson.id)
            const needsStatus = lesson.status !== 'cancelled' && hasLessonPassed(lesson)
            return (
              <LessonDayCard
                key={lesson.id}
                lesson={lesson}
                studentsCount={groupStudentsCount.get(lesson.group)}
                attendanceFilled={status?.attendanceFilled}
                homeworkCount={status?.homeworkCount}
                isEnriching={needsStatus && !status}
              />
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function emptyTitleFor(mode: 'today' | 'tomorrow', date: string): string {
  if (mode === 'tomorrow') return 'Завтра занятий нет'
  return date === todayISO() ? 'На сегодня занятий нет' : 'На эту дату занятий нет'
}

/** "Эта неделя" / "Следующая неделя" / "Предстоящие" — a bounded date-range
 * fetch (a teacher's own inherently small dataset), grouped visually by day
 * rather than a flat chronological list. */
function GroupedRangeView({ range, emptyTitle, excludePast = false }: { range: DateRange; emptyTitle: string; excludePast?: boolean }) {
  const { data: lessons, isPending, isError, refetch } = useQuery({
    queryKey: ['lessons', 'range', range],
    queryFn: () =>
      fetchAllPages<Lesson>((page) =>
        lessonsApi.list({ date_from: range.from, date_to: range.to, ordering: 'date,start_time', page }),
      ),
  })

  if (isPending) return <LoadingState label="Загружаем занятия…" />
  if (isError) return <ErrorState onRetry={() => void refetch()} />

  const visible = excludePast ? (lessons ?? []).filter((lesson) => !hasLessonPassed(lesson)) : (lessons ?? [])
  const groups = groupLessonsByDate(visible)

  if (groups.length === 0) {
    return (
      <EmptyState
        icon={CalendarDays}
        title={emptyTitle}
        action={
          <Link to="/app/schedule">
            <Button variant="secondary" size="sm">
              Открыть расписание
            </Button>
          </Link>
        }
      />
    )
  }

  return (
    <div className="space-y-6">
      {groups.map((group) => (
        <div key={group.date}>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-secondary">{dateSectionHeading(group.date)}</h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {group.lessons.map((lesson) => (
              <LessonCard key={lesson.id} lesson={lesson} compact />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/** "Все уроки" — the only tab allowed to show full history, so it keeps
 * real server-side pagination, search and filters instead of loading
 * everything at once. */
function AllLessonsView({ groupsData }: { groupsData: Group[] | undefined }) {
  const [search, setSearch] = useState('')
  const [date, setDate] = useState('')
  const [groupId, setGroupId] = useState('')
  const [subjectId, setSubjectId] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const { data: subjectsData } = useQuery({ queryKey: ['subjects', 'list'], queryFn: () => subjectsApi.list({ is_active: true }) })

  const { data, isPending, isError, refetch } = useLessons({
    search: search || undefined,
    date: date || undefined,
    group: groupId ? Number(groupId) : undefined,
    subject: subjectId ? Number(subjectId) : undefined,
    status: (status || undefined) as LessonStatus | undefined,
    ordering: '-date',
    page,
  })

  function resetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-2">
        <div className="w-full max-w-xs">
          <SearchInput value={search} onChange={resetPage(setSearch)} placeholder="Поиск по теме…" />
        </div>
        <div className="w-40">
          <DatePicker aria-label="Дата" value={date} onChange={(event) => resetPage(setDate)(event.target.value)} />
        </div>
        <div className="w-44">
          <Select
            aria-label="Группа"
            placeholder="Все группы"
            value={groupId}
            onChange={(event) => resetPage(setGroupId)(event.target.value)}
            options={(groupsData ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
          />
        </div>
        <div className="w-44">
          <Select
            aria-label="Предмет"
            placeholder="Все предметы"
            value={subjectId}
            onChange={(event) => resetPage(setSubjectId)(event.target.value)}
            options={(subjectsData?.results ?? []).map((subject) => ({ value: String(subject.id), label: subject.name }))}
          />
        </div>
        <div className="w-44">
          <Select
            aria-label="Статус"
            placeholder="Все статусы"
            value={status}
            onChange={(event) => resetPage(setStatus)(event.target.value)}
            options={STATUS_OPTIONS}
          />
        </div>
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={CalendarDays} title="Занятия не найдены" description="Попробуйте изменить фильтры или поиск." />
      ) : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((lesson) => (
              <LessonCard key={lesson.id} lesson={lesson} />
            ))}
          </div>
          <div className="mt-5">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}

const OPERATIONAL_FILTER_OPTIONS: { value: LessonOperationalStatus; label: string }[] = [
  { value: 'attendance_missing', label: OPERATIONAL_STATUS_LABELS.attendance_missing },
  { value: 'homework_missing', label: OPERATIONAL_STATUS_LABELS.homework_missing },
  { value: 'checking_pending', label: OPERATIONAL_STATUS_LABELS.checking_pending },
  { value: 'complete', label: OPERATIONAL_STATUS_LABELS.complete },
]

const OPERATIONAL_TONE: Record<LessonOperationalStatus, BadgeTone> = {
  complete: 'success',
  attendance_missing: 'danger',
  homework_missing: 'warning',
  checking_pending: 'warning',
}

/** "Завершённые" — a completed DB status is not the same as "nothing left to
 * do": this tab derives the real operational state (attendance/homework/
 * checking) for its current page and lets the teacher filter by it. */
function CompletedLessonsView({ groupsData }: { groupsData: Group[] | undefined }) {
  const [groupId, setGroupId] = useState('')
  const [operationalFilter, setOperationalFilter] = useState<LessonOperationalStatus | ''>('')
  const [page, setPage] = useState(1)

  const { data, isPending, isError, refetch } = useLessons({
    status: 'completed',
    group: groupId ? Number(groupId) : undefined,
    ordering: '-date',
    page,
  })

  const lessonIds = useMemo(() => data?.results.map((lesson) => lesson.id) ?? [], [data])
  const operationalStatus = useLessonOperationalStatus(lessonIds)

  const visibleLessons = (data?.results ?? []).filter(
    (lesson) => !operationalFilter || operationalStatus.get(lesson.id) === operationalFilter,
  )

  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-2">
        <div className="w-44">
          <Select
            aria-label="Группа"
            placeholder="Все группы"
            value={groupId}
            onChange={(event) => {
              setGroupId(event.target.value)
              setPage(1)
            }}
            options={(groupsData ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
          />
        </div>
        <div className="w-56">
          <Select
            aria-label="Статус выполнения"
            placeholder="Все статусы выполнения"
            value={operationalFilter}
            onChange={(event) => setOperationalFilter(event.target.value as LessonOperationalStatus | '')}
            options={OPERATIONAL_FILTER_OPTIONS}
          />
        </div>
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? <EmptyState icon={CheckCircle2} title="Завершённых занятий пока нет" /> : null}

      {data && data.results.length > 0 && visibleLessons.length === 0 ? (
        <EmptyState icon={ListChecks} title="На этой странице нет занятий с таким статусом" description="Попробуйте другой фильтр или страницу." />
      ) : null}

      {visibleLessons.length > 0 ? (
        <div className="space-y-2">
          {visibleLessons.map((lesson) => (
            <CompletedLessonRow key={lesson.id} lesson={lesson} status={operationalStatus.get(lesson.id)} />
          ))}
        </div>
      ) : null}

      {data && data.results.length > 0 ? (
        <div className="mt-5">
          <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
        </div>
      ) : null}
    </div>
  )
}

function CompletedLessonRow({ lesson, status }: { lesson: Lesson; status?: LessonOperationalStatus }) {
  return (
    <Link
      to={`/app/lessons/${lesson.id}`}
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3 hover:border-brand-200 hover:bg-brand-50/30"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">
          {formatDate(lesson.date, false)} · {formatTimeRange(lesson.start_time, lesson.end_time)}
        </p>
        <p className="text-sm text-ink-secondary">
          {lesson.group_name} · {lesson.subject_name ?? 'Без предмета'}
          {lesson.topic ? ` — ${lesson.topic}` : ''}
        </p>
      </div>
      {status ? <Badge tone={OPERATIONAL_TONE[status]}>{OPERATIONAL_STATUS_LABELS[status]}</Badge> : <Badge tone="muted">Проверяем…</Badge>}
    </Link>
  )
}

/** "Отменённые" — a plain filtered, paginated list; no operational status
 * applies to a lesson that never happened. */
function CancelledLessonsView({ groupsData }: { groupsData: Group[] | undefined }) {
  const [groupId, setGroupId] = useState('')
  const [page, setPage] = useState(1)

  const { data, isPending, isError, refetch } = useLessons({
    status: 'cancelled',
    group: groupId ? Number(groupId) : undefined,
    ordering: '-date',
    page,
  })

  return (
    <div>
      <div className="mb-5 w-44">
        <Select
          aria-label="Группа"
          placeholder="Все группы"
          value={groupId}
          onChange={(event) => {
            setGroupId(event.target.value)
            setPage(1)
          }}
          options={(groupsData ?? []).map((group) => ({ value: String(group.id), label: group.name }))}
        />
      </div>

      {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? <EmptyState icon={CalendarX2} title="Отменённых занятий нет" /> : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.results.map((lesson) => (
              <LessonCard key={lesson.id} lesson={lesson} />
            ))}
          </div>
          <div className="mt-5">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}
