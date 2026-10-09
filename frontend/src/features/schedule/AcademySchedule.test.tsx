import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthContext } from '@/features/auth/AuthContext'
import type { AuthContextValue } from '@/features/auth/AuthContext'
import { SchedulePage } from '@/features/schedule/SchedulePage'
import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { BoardLesson, ScheduleBoardData } from '@/types/schedule'

vi.mock('@/api/schedule', () => ({ scheduleApi: { options: vi.fn(), board: vi.fn(), freeRooms: vi.fn(), check: vi.fn() } }))
vi.mock('@/api/assistant', async (original) => {
  const actual = await original<typeof import('@/api/assistant')>()
  return { ...actual, assistantApi: { ...actual.assistantApi, moveLesson: vi.fn(), options: vi.fn().mockResolvedValue({ weekdays: [], rooms: [], teachers: [], groups: [], courses: [] }) } }
})

import { assistantApi } from '@/api/assistant'
import { scheduleApi } from '@/api/schedule'

const LESSON: BoardLesson = {
  id: 7, date: '2026-10-12', start: '10:00', end: '11:00', duration_minutes: 60,
  group: { id: 5, name: 'PRO-01' }, course: null, subject: null, teacher: { id: 1, name: 'Islam', color: '#2563EB' },
  room: { id: 10, name: 'A1' }, topic: '', lesson_number: 1, status: 'scheduled', status_display: 'Запланирован',
  students_count: 3, schedule_overridden: false,
  conflicts: [{ kind: 'teacher', kind_label: 'Тренер', message: 'Тренер «Islam»: 2 занятия пересекаются', with: [8] }],
}

const board = (canEdit: boolean): ScheduleBoardData => ({
  start: '2026-10-12', end: '2026-10-12', now: { date: '2026-10-12', time: '09:00', timezone: 'Asia/Bishkek' },
  hours: { start: '08:00', end: '24:00' }, capabilities: { can_edit: canEdit }, lessons: [LESSON],
  legend: [], conflicts: [], stats: { lessons: 1, by_status: {}, conflicts: 1, minutes: 60, free_rooms: null },
})

function renderAs(role: 'team_lead' | 'admin') {
  const auth = { user: buildUser({ role }), status: 'authenticated', login: vi.fn(), logout: vi.fn(), retry: vi.fn() } as AuthContextValue
  return renderWithProviders(<AuthContext.Provider value={auth}><SchedulePage /></AuthContext.Provider>, { route: '/app/schedule' })
}

describe('/app/schedule for Team Lead and Admin', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-12T03:00:00Z'))
    vi.mocked(scheduleApi.options).mockResolvedValue({ teachers: [], rooms: [{ id: 10, name: 'A1', capacity: 10 }], groups: [], statuses: [], hours: { start: '08:00', end: '24:00' } })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('Team Lead: the shared board, read-only lesson details with the conflict reason', async () => {
    vi.mocked(scheduleApi.board).mockResolvedValue(board(false))
    const user = userEvent.setup()
    renderAs('team_lead')
    await user.click(await within(await screen.findByTestId('time-grid')).findByRole('button', { name: /PRO-01/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Тренер «Islam»: 2 занятия пересекаются')).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: /Открыть занятие/ })).toHaveAttribute('href', '/app/lessons/7')
    expect(within(dialog).queryByRole('button', { name: 'Перенести' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Добавить занятие' })).not.toBeInTheDocument()
  })

  it('Admin: moves a lesson after the live conflict check says the time is free', async () => {
    vi.mocked(scheduleApi.board).mockResolvedValue(board(true))
    vi.mocked(scheduleApi.check).mockImplementation(async (p) => ({ date: p.date, start: p.start, end: p.end, ok: p.start !== '12:00', conflicts: p.start === '12:00'
      ? [{ kind: 'room', kind_label: 'Кабинет', message: 'Аудитория «A1» уже занята группой «PRO-02» (12:00–13:00).', lesson: { id: 9, date: p.date, start: '12:00', end: '13:00', group: { id: 6, name: 'PRO-02' }, teacher: null, room: null } }]
      : [] }))
    vi.mocked(assistantApi.moveLesson).mockResolvedValue({} as never)
    const user = userEvent.setup()
    renderAs('admin')
    expect(await screen.findByRole('button', { name: 'Добавить занятие' })).toBeInTheDocument()
    await user.click(within(screen.getByTestId('time-grid')).getByRole('button', { name: /PRO-01/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Перенести' }))
    const start = within(dialog).getByLabelText('Начало')
    const end = within(dialog).getByLabelText('Окончание')
    await user.clear(end)
    await user.type(end, '13:00')
    await user.clear(start)
    await user.type(start, '12:00')
    expect(await within(dialog).findByText(/Аудитория «A1» уже занята/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Перенести' })).toBeDisabled()
    await user.clear(start)
    await user.type(start, '12:30')
    await within(dialog).findByText('Тренер, группа и кабинет свободны в это время.')
    await user.click(within(dialog).getByRole('button', { name: 'Перенести' }))
    await waitFor(() => expect(assistantApi.moveLesson).toHaveBeenCalledWith(7, { date: '2026-10-12', start_time: '12:30', end_time: '13:00' }))
  })
})
