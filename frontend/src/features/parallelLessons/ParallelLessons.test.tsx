import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { ParallelOptions, ParallelSession, RosterGroup } from '@/types/parallelLessons'
import type { UserRole } from '@/types/auth'

let role: UserRole = 'assistant'
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('@/api/parallelLessons', () => ({
  parallelLessonsApi: {
    list: vi.fn(), get: vi.fn(), options: vi.fn(), create: vi.fn(), update: vi.fn(), check: vi.fn(), cancel: vi.fn(),
    start: vi.fn(), complete: vi.fn(), addGroup: vi.fn(), removeGroup: vi.fn(), roster: vi.fn(), markAttendance: vi.fn(),
    homework: vi.fn(), addHomework: vi.fn(), statistics: vi.fn(), history: vi.fn(), analytics: vi.fn(),
  },
}))

import { parallelLessonsApi } from '@/api/parallelLessons'

import { ParallelLessonsPage } from './ParallelLessonsPage'
import { SessionDetailPage } from './SessionDetailPage'
import { SessionFormModal } from './SessionFormModal'

const api = vi.mocked(parallelLessonsApi)

const OPTIONS: ParallelOptions = {
  teachers: [{ id: 1, name: 'Islam', color: '#2563EB' }],
  rooms: [{ id: 10, name: '101', capacity: 30 }],
  groups: [
    { id: 1, name: 'Python A', course: 'Python', students_count: 10 },
    { id: 2, name: 'Python B', course: 'Python', students_count: 8 },
    { id: 3, name: 'Frontend A', course: 'Frontend', students_count: 10 },
    { id: 4, name: 'English A', course: 'English', students_count: 8 },
  ],
  subjects: [],
  statuses: [],
}

const CAPS = {
  can_edit: true, can_change_schedule: true, can_manage_groups: true, can_cancel: true, can_start: true,
  can_complete: true, can_mark_attendance: true, can_add_homework: true,
}

function session(over: Partial<ParallelSession> = {}): ParallelSession {
  const groups = OPTIONS.groups.map((g, i) => ({
    id: i + 1, group: { id: g.id, name: g.name }, lesson: 100 + i, lesson_status: 'scheduled', program: null,
    status: 'active' as const, status_display: 'Участвует', students_count: g.students_count, added_at: '', removed_at: null, removal_reason: '',
  }))
  return {
    id: 105, date: '2026-11-26', start_time: '15:00:00', end_time: '16:00:00', teacher: { id: 1, name: 'Islam', color: '#2563EB' },
    room: { id: 10, name: '101' }, subject: null, topic: 'Общая тема', description: '', notes: '', youtube_url: '', presentation_urls: [],
    status: 'scheduled', status_display: 'Запланировано', cancellation_reason: '', groups, groups_count: 4, students_count: 36,
    created_by_name: 'Assist', completed_at: null, completed_by_name: null, cancelled_at: null, created_at: '', updated_at: '',
    capabilities: CAPS, ...over,
  }
}

beforeEach(() => {
  role = 'assistant'
  api.options.mockResolvedValue(OPTIONS)
  api.list.mockResolvedValue({ count: 1, next: null, previous: null, results: [session()] })
  api.analytics.mockResolvedValue({
    start: '2026-11-01', end: '2026-11-26',
    totals: { sessions: 1, scheduled: 1, in_progress: 0, completed: 0, cancelled: 0, group_participations: 4, groups: 4, students: 36 },
    workload: [{ teacher: { id: 1, name: 'Islam' }, sessions: 1, completed: 0, groups: 4, minutes: 0 }],
    attendance_by_group: [],
  })
  api.check.mockResolvedValue({ ok: true, conflicts: [] })
})

afterEach(() => vi.clearAllMocks())

describe('ParallelLessonsPage', () => {
  it('lists sessions with their groups, students and status; staff may create', async () => {
    renderWithProviders(<ParallelLessonsPage />, { route: '/assistant/parallel-lessons' })
    const list = await screen.findByRole('list', { name: 'Параллельные занятия' })
    expect(within(list).getByText('Общая тема')).toBeInTheDocument()
    for (const name of ['Python A', 'Python B', 'Frontend A', 'English A']) expect(within(list).getByText(name)).toBeInTheDocument()
    expect(within(list).getByText(/36 студ\./)).toBeInTheDocument()
    expect(within(list).getByText('Запланировано')).toBeInTheDocument()
    expect(within(list).getByRole('link')).toHaveAttribute('href', '/assistant/parallel-lessons/105')
    expect(screen.getByRole('button', { name: 'Создать занятие' })).toBeInTheDocument()
    expect(screen.getByText('Нагрузка тренеров')).toBeInTheDocument()
  })

  it('a trainer sees their sessions without create or academy-wide filters', async () => {
    role = 'teacher'
    renderWithProviders(<ParallelLessonsPage />, { route: '/app/parallel-lessons' })
    await screen.findByRole('list', { name: 'Параллельные занятия' })
    expect(screen.queryByRole('button', { name: 'Создать занятие' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Тренер')).not.toBeInTheDocument()
    expect(api.options).not.toHaveBeenCalled()
  })

  it('passes filters to the API', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ParallelLessonsPage />, { route: '/app/parallel-lessons' })
    await screen.findByRole('list', { name: 'Параллельные занятия' })
    await user.selectOptions(screen.getByLabelText('Статус'), 'completed')
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'completed', page: 1 })))
  })
})

describe('SessionFormModal', () => {
  async function fill(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByRole('option', { name: /101/ })
    await user.selectOptions(screen.getByLabelText(/Аудитория/), '10')
    await user.selectOptions(screen.getByLabelText(/Тренер/), '1')
    await user.type(screen.getByLabelText(/Дата/), '2026-11-26')
    const groups = screen.getByRole('list', { name: 'Группы' })
    for (const name of ['Python A', 'Python B', 'Frontend A', 'English A']) await user.click(within(groups).getByLabelText(new RegExp(name)))
  }

  it('selects any number of groups and creates the session once it is conflict-free', async () => {
    const user = userEvent.setup()
    api.create.mockResolvedValue(session())
    renderWithProviders(<SessionFormModal onClose={vi.fn()} />)
    await fill(user)
    expect(screen.getByText(/4 выбрано · 36 студентов/)).toBeInTheDocument()
    await screen.findByText('Тренер, аудитория и все группы свободны в это время.')
    await user.click(screen.getByRole('button', { name: 'Создать занятие' }))
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(expect.objectContaining({
      room: 10, teacher: 1, date: '2026-11-26', start_time: '15:00', end_time: '16:00', groups: [1, 2, 3, 4],
    })))
  })

  it('shows conflicts before saving and blocks the save', async () => {
    const user = userEvent.setup()
    api.check.mockResolvedValue({ ok: false, conflicts: [{ kind: 'teacher', kind_label: 'Тренер', message: 'Тренер «Islam» уже ведёт занятие в группе «X» (15:30–16:30).' }] })
    renderWithProviders(<SessionFormModal onClose={vi.fn()} />)
    await fill(user)
    expect(await screen.findByText(/уже ведёт занятие в группе «X»/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать занятие' })).toBeDisabled()
    expect(api.check).toHaveBeenLastCalledWith(expect.objectContaining({ groups: [1, 2, 3, 4], teacher: 1, room: 10 }))
  })
})

describe('SessionDetailPage', () => {
  const roster: RosterGroup[] = [
    { group: { id: 1, name: 'Python A' }, lesson: 100, lesson_status: 'scheduled', students: [
      { student: 11, student_name: 'Aida A', status: null, status_display: null, comment: '', excuse_reason: '' },
      { student: 12, student_name: 'Bek A', status: null, status_display: null, comment: '', excuse_reason: '' },
    ] },
    { group: { id: 2, name: 'Python B' }, lesson: 101, lesson_status: 'scheduled', students: [
      { student: 21, student_name: 'Cholpon B', status: 'present', status_display: 'Присутствовал', comment: '', excuse_reason: '' },
    ] },
  ]

  function renderDetail(over: Partial<ParallelSession> = {}) {
    api.get.mockResolvedValue(session(over))
    api.roster.mockResolvedValue(roster)
    api.markAttendance.mockResolvedValue({ roster })
    return renderWithProviders(
      <Routes><Route path="/app/parallel-lessons/:id" element={<SessionDetailPage />} /></Routes>,
      { route: '/app/parallel-lessons/105' },
    )
  }

  it('marks attendance group by group, never mixing students', async () => {
    role = 'teacher'
    const user = userEvent.setup()
    renderDetail()
    expect(await screen.findByRole('heading', { name: 'Общая тема' })).toBeInTheDocument()
    const nav = await screen.findByRole('navigation', { name: 'Группы занятия' })
    expect(within(nav).getByText('0/2')).toBeInTheDocument()
    expect(within(nav).getByText('1/1')).toBeInTheDocument()
    expect(screen.queryByText('Cholpon B')).not.toBeInTheDocument()

    await user.click(within(screen.getByRole('radiogroup', { name: 'Отметка: Aida A' })).getByRole('radio', { name: 'Присутствовал' }))
    await user.click(within(screen.getByRole('radiogroup', { name: 'Отметка: Bek A' })).getByRole('radio', { name: 'Отсутствовал' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.markAttendance).toHaveBeenCalledWith(105, 1, [
      { student: 11, status: 'present' }, { student: 12, status: 'absent' },
    ]))

    await user.click(within(nav).getByText('Python B'))
    expect(screen.getByText('Cholpon B')).toBeInTheDocument()
    expect(screen.queryByText('Aida A')).not.toBeInTheDocument()
  })

  it('completes the session and shows per-group errors from the backend', async () => {
    const user = userEvent.setup()
    const { AxiosError } = await import('axios')
    api.complete.mockRejectedValue(new AxiosError('Bad', '400', undefined, undefined, {
      status: 400, data: { completion: ['«Python B»: Посещаемость отмечена'] }, statusText: '', headers: {}, config: {} as never,
    }))
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Завершить' }))
    expect(await screen.findByText(/«Python B»: Посещаемость отмечена/)).toBeInTheDocument()
    expect(api.complete).toHaveBeenCalledWith(105)
  })

  it('hides actions the backend does not allow', async () => {
    renderDetail({ status: 'completed', status_display: 'Проведено', capabilities: { ...CAPS, can_edit: false, can_cancel: false, can_start: false, can_complete: false, can_manage_groups: false, can_change_schedule: false } })
    await screen.findByRole('heading', { name: 'Общая тема' })
    for (const name of ['Изменить', 'Отменить', 'Начать', 'Завершить']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
  })
})

describe('schedule calendar integration', () => {
  it('marks a parallel session lesson on the board with a distinct indicator', async () => {
    const { LessonCard } = await import('@/features/scheduleBoard/LessonCard')
    const base = {
      id: 1, date: '2026-11-26', start: '15:00', end: '16:00', duration_minutes: 60, group: { id: 1, name: 'Python A' }, course: null,
      subject: null, teacher: { id: 1, name: 'Islam', color: '#2563EB' }, room: { id: 10, name: '101' }, topic: '', lesson_number: 9,
      status: 'scheduled' as const, status_display: 'Запланирован', students_count: 10, schedule_overridden: true, conflicts: [],
    }
    const { rerender } = renderWithProviders(<LessonCard lesson={{ ...base, parallel_session: { id: 105, groups_count: 4 } }} onOpen={vi.fn()} />)
    const card = screen.getByRole('button')
    expect(card).toHaveAttribute('data-parallel-session', '105')
    expect(within(card).getByLabelText('Параллельное занятие')).toBeInTheDocument()
    expect(card.getAttribute('aria-label')).toContain('Параллельное занятие · 4 групп')
    rerender(<LessonCard lesson={{ ...base, parallel_session: null }} onOpen={vi.fn()} />)
    expect(screen.queryByLabelText('Параллельное занятие')).not.toBeInTheDocument()
  })
})
