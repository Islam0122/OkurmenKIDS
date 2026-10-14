import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { GroupBoard, LeaderboardGroup, LeaderboardMeta, LeaderboardStudent, StudentBoard } from '@/types/leaderboard'

import { addDays, periodTitle, plural, weekRangeLabel } from './format'
import { GroupsLeaderboardPage, StudentsLeaderboardPage } from './LeaderboardPages'

vi.mock('@/api/publicLeaderboard', () => ({ publicLeaderboardApi: { meta: vi.fn(), students: vi.fn(), groups: vi.fn() } }))
// The public site must never touch the authenticated client.
vi.mock('@/api/client', async (original) => {
  const actual = await original<typeof import('@/api/client')>()
  const fail = () => { throw new Error('the public site used the authenticated API client') }
  return { ...actual, apiClient: { get: fail, post: fail, put: fail, patch: fail, delete: fail } }
})

import { publicLeaderboardApi } from '@/api/publicLeaderboard'

const api = vi.mocked(publicLeaderboardApi)

const META: LeaderboardMeta = {
  today: '2026-10-14', timezone: 'Asia/Bishkek', current: { year: 2026, month: 10, week_start: '2026-10-12' },
  first_date: '2025-09-01', years: [2026, 2025],
  groups: [{ key: 'grpa', name: 'Prog 1', course: 'crsa' }, { key: 'grpb', name: 'Design 1', course: 'crsb' }],
  courses: [{ key: 'crsa', name: 'Prog SOFT' }, { key: 'crsb', name: 'Design' }],
  rules: { attendance_present: 10, attendance_late: 5, homework_done: 10, homework_late: 5, homework_grade_max: 10, test_max: 20,
    group_method: 'average', week_starts: 'monday', timezone: 'Asia/Bishkek' },
  last_activity: '2026-10-14T05:00:00Z',
}

function student(rank: number, name: string, over: Partial<LeaderboardStudent> = {}): LeaderboardStudent {
  return {
    key: `st${rank}${name.length}`, rank, name, initials: name.slice(0, 1), hidden: false,
    group: { key: 'grpa', name: 'Prog 1' }, course: { key: 'crsa', name: 'Prog SOFT' },
    xp: 100 - rank, breakdown: { attendance: 50, homework: 30, tests: 20 - rank }, change: null, ...over,
  }
}

const STUDENTS = [
  student(1, 'Алия С.', { change: { status: 'up', value: 3 } }),
  student(2, 'Бакыт А.', { change: { status: 'down', value: -2 } }),
  student(3, 'Чынара О.', { change: { status: 'new', value: 0 }, group: { key: 'grpb', name: 'Design 1' } }),
  student(4, 'Скрытый участник', { hidden: true, initials: '', group: null, course: null, change: { status: 'same', value: 0 } }),
]

function studentBoard(results = STUDENTS, over: Partial<StudentBoard> = {}): StudentBoard {
  return {
    period: { type: 'month', start: '2026-10-01', end: '2026-10-31', is_current: true, year: 2026, month: 10 },
    previous_period: { type: 'month', start: '2026-09-01', end: '2026-09-30', is_current: false, year: 2026, month: 9 },
    generated_at: '2026-10-14T05:00:00Z', participants: results.length, podium: results.slice(0, 3),
    count: results.length, page: 1, page_size: 20, num_pages: 1, results, ...over,
  }
}

const GROUP: LeaderboardGroup = {
  key: 'grpb', rank: 1, name: 'Design 1', course: { key: 'crsb', name: 'Design' }, members: 4, active_students: 3,
  total_xp: 120, average_xp: 30, top_members: [{ name: 'Чынара О.', initials: 'ЧО', xp: 60 }], change: { status: 'up', value: 1 },
}

function groupBoard(results: LeaderboardGroup[] = [GROUP, { ...GROUP, key: 'grpa', rank: 2, name: 'Prog 1', average_xp: 20.5, change: null }]): GroupBoard {
  return { ...studentBoard([]), participants: results.length, podium: results.slice(0, 3), count: results.length, results, students_ranked: 4 } as GroupBoard
}

function renderSite(route = '/leaderboard') {
  return renderWithProviders(
    <Routes>
      <Route path="/leaderboard" element={<StudentsLeaderboardPage />} />
      <Route path="/leaderboard/groups" element={<GroupsLeaderboardPage />} />
    </Routes>,
    { route },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue(META)
  api.students.mockResolvedValue(studentBoard())
  api.groups.mockResolvedValue(groupBoard())
})

describe('format helpers', () => {
  it('labels periods in the academy calendar', () => {
    expect(addDays('2026-12-28', 6)).toBe('2027-01-03')
    expect(weekRangeLabel('2026-10-12')).toBe('12–18 октября 2026')
    expect(weekRangeLabel('2026-09-28')).toBe('28 сентября — 4 октября 2026')
    expect(periodTitle({ type: 'year', start: '2025-01-01', end: '2025-12-31', is_current: false })).toBe('2025 год')
    expect(plural(21, ['студент', 'студента', 'студентов'])).toBe('студент')
    expect(plural(12, ['студент', 'студента', 'студентов'])).toBe('студентов')
  })
})

describe('Топ студентов', () => {
  it('shows the podium, the table with changes and the participants count', async () => {
    renderSite()
    const podium = await screen.findByRole('list', { name: 'Три лучших студента' })
    expect(within(podium).getByText('Алия С.')).toBeInTheDocument()
    expect(within(podium).getAllByText(/XP$/)).toHaveLength(3)
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(5)
    expect(within(table).getByText('+3')).toBeInTheDocument()
    expect(within(table).getByText('−2')).toBeInTheDocument()
    expect(within(table).getByText('NEW')).toBeInTheDocument()
    expect(within(table).getByText('Скрытый участник')).toBeInTheDocument()
    expect(screen.getByText('4 студента')).toBeInTheDocument()
    expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ period: 'month', year: 2026, month: 10, page: 1 }))
  })

  it('switching to year or week asks the server for exactly that period', async () => {
    const user = userEvent.setup()
    renderSite()
    await screen.findByRole('table')
    await user.click(screen.getByRole('radio', { name: 'Год' }))
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ period: 'year', year: 2026 })))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Год' }), '2025')
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ period: 'year', year: 2025 })))
    await user.click(screen.getByRole('radio', { name: 'Неделя' }))
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ period: 'week', week_start: '2026-10-12' })))
    expect(screen.getByRole('button', { name: 'Следующая неделя' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Предыдущая неделя' }))
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ period: 'week', week_start: '2026-10-05' })))
  })

  it('opens the period from the URL', async () => {
    renderSite('/leaderboard?period=month&year=2025&month=3')
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ period: 'month', year: 2025, month: 3 })))
  })

  it('search, group filter and sort go to the server together with the period', async () => {
    const user = userEvent.setup()
    renderSite()
    await screen.findByRole('table')
    await user.type(screen.getByRole('searchbox', { name: 'Поиск студента' }), 'али')
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ q: 'али', period: 'month' })))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Группа' }), 'grpb')
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ group: 'grpb', q: 'али' })))
    await user.click(screen.getByRole('button', { name: /Сортировка/ }))
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ order: 'asc' })))
  })

  it('loads more rows page by page', async () => {
    const user = userEvent.setup()
    api.students.mockImplementation(async (params) =>
      params.page === 2
        ? studentBoard([student(21, 'Данияр Б.')], { page: 2, num_pages: 2, count: 21 })
        : studentBoard(STUDENTS, { page: 1, num_pages: 2, count: 21 }),
    )
    renderSite()
    await user.click(await screen.findByRole('button', { name: 'Показать ещё' }))
    expect(await within(screen.getByRole('table')).findByText('Данияр Б.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Показать ещё' })).not.toBeInTheDocument()
  })

  it('shows an empty state for a period without results', async () => {
    api.students.mockResolvedValue(studentBoard([]))
    renderSite()
    expect(await screen.findByText('Рейтинг пуст')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows an error with a working retry', async () => {
    const user = userEvent.setup()
    api.students.mockRejectedValueOnce(new Error('Network Error'))
    renderSite()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Не удалось загрузить рейтинг')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })
})

describe('Топ групп', () => {
  it('ranks groups by average XP and opens a group’s students', async () => {
    const user = userEvent.setup()
    renderSite('/leaderboard/groups')
    const list = await screen.findByRole('list', { name: 'Рейтинг групп' })
    expect(within(list).getByText('Prog 1')).toBeInTheDocument()
    expect(within(list).getByText('20,5')).toBeInTheDocument()
    expect(screen.getByText(/среднему XP на студента/)).toBeInTheDocument()
    const toggle = within(list).getByRole('button', { name: /Design 1/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await waitFor(() => expect(api.students).toHaveBeenCalledWith(expect.objectContaining({ group: 'grpb', period: 'month' })))
  })
})
