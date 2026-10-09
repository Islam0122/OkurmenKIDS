import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/api/client'
import { AuthContext } from '@/features/auth/AuthContext'
import type { AuthContextValue } from '@/features/auth/AuthContext'
import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { BoardLesson, ScheduleBoardData } from '@/types/schedule'

import { SiteSchedulePage } from './SchedulePage'
import { SiteAccess } from './SiteAccess'

vi.mock('@/api/schedule', () => ({ scheduleApi: { options: vi.fn(), board: vi.fn(), freeRooms: vi.fn(), check: vi.fn() } }))

import { scheduleApi } from '@/api/schedule'

const LONG_GROUP = 'Prog SOFT 1 — вечерняя группа продвинутого уровня'
const FULL_NAME = 'Айжаркын Өмүрбекова-Сыдыкбекова'

function lesson(over: Partial<BoardLesson> = {}): BoardLesson {
  return {
    id: 1, date: '2026-10-12', start: '14:00', end: '15:30', duration_minutes: 90,
    group: { id: 5, name: LONG_GROUP }, course: { id: 1, name: 'Prog' }, subject: { id: 3, name: 'Python' },
    teacher: { id: 1, name: FULL_NAME, color: '#2563EB' }, room: { id: 10, name: 'Кабинет 201 (большой)' },
    topic: 'Циклы', lesson_number: 4, status: 'scheduled', status_display: 'Запланирован',
    students_count: 9, schedule_overridden: false, conflicts: [], ...over,
  }
}

function board(start: string, end: string, lessons = [lesson(), lesson({ id: 2, start: '16:00', end: '17:00', duration_minutes: 60,
  group: { id: 6, name: 'Robo-2' }, teacher: { id: 2, name: 'Бакыт Асанов', color: '#D97706' }, room: { id: 11, name: 'B2' } })]): ScheduleBoardData {
  return {
    start, end, now: { date: '2026-10-12', time: '11:00', timezone: 'Asia/Bishkek' }, hours: { start: '08:00', end: '24:00' },
    capabilities: { can_edit: true }, lessons, legend: [], conflicts: [],
    stats: { lessons: lessons.length, by_status: {}, conflicts: 0, minutes: 150, free_rooms: { mode: 'now', free: 1, total: 2, date: start, at: '11:00' } },
  }
}

function renderSite(route: string, role: UserRole = 'assistant') {
  const auth = { user: buildUser({ role }), status: 'authenticated', login: vi.fn(), logout: vi.fn(), retry: vi.fn() } as AuthContextValue
  return renderWithProviders(
    <AuthContext.Provider value={auth}>
      <Routes>
        <Route path="/schedule" element={<SiteAccess />}>
          <Route path="day" element={<SiteSchedulePage view="day" />} />
          <Route path="week" element={<SiteSchedulePage view="week" />} />
        </Route>
      </Routes>
    </AuthContext.Provider>,
    { route },
  )
}

describe('OkurmenKIDS Schedule (read-only site)', () => {
  const writes = { post: vi.spyOn(apiClient, 'post'), put: vi.spyOn(apiClient, 'put'), patch: vi.spyOn(apiClient, 'patch'), delete: vi.spyOn(apiClient, 'delete') }

  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-12T05:00:00Z'))
    vi.mocked(scheduleApi.options).mockResolvedValue({
      teachers: [{ id: 1, name: FULL_NAME, color: '#2563EB' }, { id: 2, name: 'Бакыт Асанов', color: '#D97706' }],
      rooms: [{ id: 10, name: 'Кабинет 201 (большой)', capacity: 12 }, { id: 11, name: 'B2', capacity: 8 }],
      groups: [{ id: 5, name: LONG_GROUP, course: 'Prog' }], statuses: [], hours: { start: '08:00', end: '24:00' },
    })
    vi.mocked(scheduleApi.board).mockImplementation(async (p) => board(p.start, p.end))
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('shows the day 08:00–24:00 with full group, trainer and room names', async () => {
    renderSite('/schedule/day?date=2026-10-12')
    const grid = await screen.findByTestId('site-grid')
    expect(within(grid).getByText('08:00')).toBeInTheDocument()
    expect(within(grid).getByText('24:00')).toBeInTheDocument()
    expect(within(grid).getByText(LONG_GROUP)).toBeInTheDocument()
    expect(within(grid).getAllByText(FULL_NAME).length).toBeGreaterThan(0)
    expect(within(grid).getAllByText('Кабинет 201 (большой)').length).toBeGreaterThan(0)
    expect(grid.innerHTML).not.toContain('truncate')
    expect(vi.mocked(scheduleApi.board).mock.calls[0][0]).toMatchObject({ start: '2026-10-12', end: '2026-10-12' })
  })

  it('filters on the server by trainer, room and group, keeping them in the URL across views', async () => {
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    await screen.findByTestId('site-grid')
    await user.selectOptions(screen.getByLabelText('Тренер'), '2')
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({ teacher: 2 }))
    await user.click(screen.getByRole('button', { name: /Кабинет: Все кабинеты/ }))
    await user.click(screen.getByRole('option', { name: /B2/ }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({ teacher: 2, room: [11] }))
    await user.selectOptions(screen.getByLabelText('Группа'), '5')
    await user.click(screen.getByRole('radio', { name: 'Неделя' }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({
      start: '2026-10-12', end: '2026-10-18', teacher: 2, room: [11], group: 5,
    }))
    expect(await screen.findByTestId('site-week')).toBeInTheDocument()
  })

  it('searches the loaded lessons by group, trainer or room', async () => {
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    const grid = await screen.findByTestId('site-grid')
    await user.type(screen.getByLabelText('Поиск'), 'бакыт')
    await waitFor(() => expect(within(grid).queryByText(LONG_GROUP)).not.toBeInTheDocument())
    expect(within(screen.getByTestId('site-grid')).getByText('Robo-2')).toBeInTheDocument()
  })

  it('shows lesson details without any action that changes data', async () => {
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    const grid = await screen.findByTestId('site-grid')
    await user.click(within(grid).getByRole('button', { name: new RegExp(LONG_GROUP) }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Кабинет 201 (большой)')).toBeInTheDocument()
    for (const label of ['Перенести', 'Отменить', 'Сохранить', 'Удалить', 'Добавить занятие']) {
      expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument()
    }
    expect(writes.post).not.toHaveBeenCalled()
    expect(writes.put).not.toHaveBeenCalled()
    expect(writes.patch).not.toHaveBeenCalled()
    expect(writes.delete).not.toHaveBeenCalled()
  })

  it('finds free rooms for a time window', async () => {
    vi.mocked(scheduleApi.freeRooms).mockResolvedValue({
      date: '2026-10-12', start: '11:00', end: '12:00', free_count: 1, busy_count: 1, rooms: [
        { room: { id: 11, name: 'B2', capacity: 8 }, is_free: true, lessons_count: 0, busy: [], conflicting_lessons: [], free_at: null, free_window: { start: '08:00', end: '24:00' }, next_free: null },
        { room: { id: 10, name: 'Кабинет 201 (большой)', capacity: 12 }, is_free: false, lessons_count: 1, busy: [{ start: '10:30', end: '12:30' }],
          conflicting_lessons: [{ id: 9, date: '2026-10-12', start: '10:30', end: '12:30', group: { id: 5, name: LONG_GROUP }, teacher: { id: 1, name: FULL_NAME }, room: null }],
          free_at: '12:30', free_window: null, next_free: { start: '12:30', end: '14:00' } },
      ],
    })
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    await screen.findByTestId('site-grid')
    await user.click(screen.getByRole('button', { name: 'Свободные кабинеты' }))
    const panel = await screen.findByRole('dialog', { name: 'Свободные кабинеты' })
    expect(await within(panel).findByText(/Освободится в/)).toHaveTextContent('12:30')
    expect(within(panel).getByText(LONG_GROUP)).toBeInTheDocument()
  })

  it('re-reads the schedule every minute and on window focus', async () => {
    const { REFRESH_MS } = await import('./SchedulePage')
    expect(REFRESH_MS).toBe(60_000)
  })

  it('a trainer gets the no-access page and no schedule request', async () => {
    renderSite('/schedule/day', 'teacher')
    expect(await screen.findByText('Нет доступа к расписанию академии')).toBeInTheDocument()
    expect(scheduleApi.board).not.toHaveBeenCalled()
  })

  it('Team Lead sees the same read-only site', async () => {
    renderSite('/schedule/day?date=2026-10-12', 'team_lead')
    expect(await screen.findByTestId('site-grid')).toBeInTheDocument()
  })
})
