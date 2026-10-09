import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BoardLesson, FreeRoomsData, ScheduleBoardData, ScheduleOptions } from '@/types/schedule'
import { renderWithProviders } from '@/test/testUtils'

import { ScheduleBoard } from './ScheduleBoard'

vi.mock('@/api/schedule', () => ({ scheduleApi: { options: vi.fn(), board: vi.fn(), freeRooms: vi.fn(), check: vi.fn() } }))

import { scheduleApi } from '@/api/schedule'

const OPTIONS: ScheduleOptions = {
  teachers: [{ id: 1, name: 'Islam', color: '#2563EB' }, { id: 2, name: 'Aibek', color: '#D97706' }],
  rooms: [{ id: 10, name: 'A1', capacity: 12 }, { id: 11, name: 'B2', capacity: 8 }],
  groups: [{ id: 5, name: 'PRO-01', course: 'Prog' }],
  statuses: [],
  hours: { start: '08:00', end: '24:00' },
}

function lesson(over: Partial<BoardLesson> = {}): BoardLesson {
  return {
    id: 1, date: '2026-10-12', start: '14:00', end: '15:30', duration_minutes: 90,
    group: { id: 5, name: 'PRO-01' }, course: { id: 1, name: 'Prog' }, subject: { id: 3, name: 'Python' },
    teacher: { id: 1, name: 'Islam', color: '#2563EB' }, room: { id: 10, name: 'A1' },
    topic: 'Циклы', lesson_number: 4, status: 'scheduled', status_display: 'Запланирован',
    students_count: 9, schedule_overridden: false, conflicts: [], ...over,
  }
}

function board(over: Partial<ScheduleBoardData> = {}, lessons: BoardLesson[] = [lesson()]): ScheduleBoardData {
  return {
    start: '2026-10-12', end: '2026-10-12',
    now: { date: '2026-10-12', time: '11:00', timezone: 'Asia/Bishkek' },
    hours: { start: '08:00', end: '24:00' },
    capabilities: { can_edit: true },
    lessons,
    legend: [{ id: 1, name: 'Islam', color: '#2563EB', lessons_count: lessons.length }],
    conflicts: [],
    stats: { lessons: lessons.length, by_status: {}, conflicts: 0, minutes: 90, free_rooms: { mode: 'now', free: 2, total: 2, date: '2026-10-12', at: '11:00' } },
    ...over,
  }
}

describe('ScheduleBoard', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-12T05:00:00Z'))
    vi.mocked(scheduleApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(scheduleApi.board).mockImplementation(async (params) => board({ start: params.start, end: params.end }))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  const render = (props: Partial<Parameters<typeof ScheduleBoard>[0]> = {}) =>
    renderWithProviders(<ScheduleBoard storageKey="test.board" onOpenLesson={vi.fn()} onAddLesson={vi.fn()} {...props} />)

  it('shows a day as a 08:00–24:00 grid with a column per room, the legend and counters', async () => {
    render()
    const grid = await screen.findByTestId('time-grid')
    expect(within(grid).getByText('08:00')).toBeInTheDocument()
    expect(within(grid).getByText('24:00')).toBeInTheDocument()
    expect(within(grid).getByText('A1')).toBeInTheDocument()
    expect(within(grid).getByText('B2')).toBeInTheDocument()
    expect(within(grid).getAllByRole('button', { name: /PRO-01.*Тренер: Islam.*Кабинет: A1/ }).length).toBe(1)
    expect(screen.getByRole('button', { name: /Islam/, pressed: false })).toBeInTheDocument()
    expect(screen.getByText(/Свободно сейчас/)).toBeInTheDocument()
    expect(vi.mocked(scheduleApi.board).mock.calls[0][0]).toMatchObject({ start: '2026-10-12', end: '2026-10-12' })
  })

  it('filters by rooms right away and combines with the trainer', async () => {
    const user = userEvent.setup()
    render()
    await screen.findByTestId('time-grid')
    await user.click(screen.getByRole('button', { name: /Кабинет: Все кабинеты/ }))
    await user.click(screen.getByRole('option', { name: /A1/ }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0].room).toEqual([10]))
    await user.click(screen.getByRole('option', { name: /B2/ }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0].room).toEqual([10, 11]))
    await user.selectOptions(screen.getByLabelText('Тренер'), '2')
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({ teacher: 2, room: [10, 11] }))
    await user.click(screen.getAllByRole('button', { name: 'Очистить фильтры' })[0])
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({ teacher: undefined, room: undefined }))
  })

  it('keeps filters when switching day/week and across a remount (session)', async () => {
    const user = userEvent.setup()
    const { unmount } = render()
    await screen.findByTestId('time-grid')
    await user.selectOptions(screen.getByLabelText('Группа'), '5')
    await user.click(screen.getByRole('radio', { name: 'Неделя' }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({ start: '2026-10-12', end: '2026-10-18', group: 5 }))
    unmount()
    vi.mocked(scheduleApi.board).mockClear()
    render()
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls[0][0]).toMatchObject({ end: '2026-10-18', group: 5 }))
    expect(screen.getByRole('radio', { name: 'Неделя' })).toHaveAttribute('aria-checked', 'true')
  })

  it('moves by day and back to today', async () => {
    const user = userEvent.setup()
    render()
    await screen.findByTestId('time-grid')
    await user.click(screen.getByRole('button', { name: 'Следующий день' }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0].start).toBe('2026-10-13'))
    await user.click(screen.getByRole('button', { name: 'Сегодня' }))
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0].start).toBe('2026-10-12'))
  })

  it('is read-only for a user who cannot edit (Team Lead)', async () => {
    vi.mocked(scheduleApi.board).mockResolvedValue(board({ capabilities: { can_edit: false } }))
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render({ onOpenLesson: onOpen })
    await screen.findByTestId('time-grid')
    expect(screen.getByText('Только просмотр')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Добавить занятие' })).not.toBeInTheDocument()
    await user.click(within(screen.getByTestId('time-grid')).getByRole('button', { name: /PRO-01/ }))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), false)
  })

  it('offers «Добавить занятие» to an editor', async () => {
    const onAdd = vi.fn()
    const user = userEvent.setup()
    render({ onAddLesson: onAdd })
    await screen.findByTestId('time-grid')
    await user.click(screen.getByRole('button', { name: 'Добавить занятие' }))
    expect(onAdd).toHaveBeenCalled()
  })

  it('explains conflicts', async () => {
    const clash = lesson({ conflicts: [{ kind: 'room', kind_label: 'Кабинет', message: 'Кабинет «A1»: 2 занятия пересекаются', with: [2] }] })
    vi.mocked(scheduleApi.board).mockResolvedValue(board({
      conflicts: [{ kind: 'room', kind_label: 'Кабинет', name: 'A1', date: '2026-10-12', message: 'x', lessons: [
        { id: 1, date: '2026-10-12', start: '14:00', end: '15:30', group: { id: 5, name: 'PRO-01' }, teacher: null, room: null },
      ] }],
      stats: { lessons: 1, by_status: {}, conflicts: 1, minutes: 90, free_rooms: null },
    }, [clash]))
    const user = userEvent.setup()
    render()
    await user.click(await screen.findByRole('button', { name: /Конфликты: 1/ }))
    expect(screen.getByRole('region', { name: 'Конфликты в расписании' })).toHaveTextContent('Кабинет «A1»')
    expect(within(screen.getByTestId('time-grid')).getByRole('button', { name: /Конфликт: Кабинет «A1»/ })).toBeInTheDocument()
  })

  it('shows an empty day', async () => {
    vi.mocked(scheduleApi.board).mockResolvedValue(board({}, []))
    render()
    expect(await screen.findByText(/В этот день занятий нет/)).toBeInTheDocument()
  })

  it('shows an error with retry', async () => {
    vi.mocked(scheduleApi.board).mockRejectedValue(new Error('boom'))
    render()
    expect(await screen.findByRole('button', { name: /Повторить|Попробовать/ })).toBeInTheDocument()
  })

  it('finds free rooms for a time window and opens a room’s schedule', async () => {
    const free: FreeRoomsData = {
      date: '2026-10-12', start: '15:00', end: '16:00', free_count: 1, busy_count: 1,
      rooms: [
        { room: { id: 11, name: 'B2', capacity: 8 }, is_free: true, lessons_count: 0, busy: [], conflicting_lessons: [], free_at: null, free_window: { start: '08:00', end: '24:00' }, next_free: null },
        { room: { id: 10, name: 'A1', capacity: 12 }, is_free: false, lessons_count: 1, busy: [{ start: '14:00', end: '15:30' }],
          conflicting_lessons: [{ id: 1, date: '2026-10-12', start: '14:00', end: '15:30', group: { id: 5, name: 'PRO-01' }, teacher: { id: 1, name: 'Islam' }, room: { id: 10, name: 'A1' } }],
          free_at: '15:30', free_window: null, next_free: { start: '15:30', end: '24:00' } },
      ],
    }
    vi.mocked(scheduleApi.freeRooms).mockResolvedValue(free)
    const user = userEvent.setup()
    render()
    await screen.findByTestId('time-grid')
    await user.click(screen.getAllByRole('button', { name: 'Свободные кабинеты' })[0])
    const panel = await screen.findByRole('dialog', { name: 'Свободные кабинеты' })
    await within(panel).findByText(/свободно 1 из 2/)
    expect(vi.mocked(scheduleApi.freeRooms).mock.calls[0][0]).toMatchObject({ date: '2026-10-12', start: '11:00', end: '12:00' })
    expect(within(panel).getByText(/Освободится в/)).toHaveTextContent('15:30')
    expect(within(panel).getByText(/Свободен 08:00–24:00/)).toBeInTheDocument()
    await user.click(within(panel).getAllByRole('button', { name: 'Расписание кабинета' })[1])
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0].room).toEqual([10]))
  })

  it('refuses an end time before the start in the free-rooms search', async () => {
    vi.mocked(scheduleApi.freeRooms).mockResolvedValue({ date: '2026-10-12', start: '11:00', end: '12:00', free_count: 0, busy_count: 0, rooms: [] })
    const user = userEvent.setup()
    render()
    await screen.findByTestId('time-grid')
    await user.click(screen.getAllByRole('button', { name: 'Свободные кабинеты' })[0])
    const panel = await screen.findByRole('dialog', { name: 'Свободные кабинеты' })
    const end = within(panel).getByLabelText('Время окончания')
    await user.clear(end)
    await user.type(end, '10:00')
    expect(await within(panel).findByRole('alert')).toHaveTextContent('Время окончания должно быть позже')
  })

  it('folds too many parallel lessons of a week day into one block that opens the day', async () => {
    const crowd = [1, 2, 3, 4].map((id) => lesson({ id, group: { id, name: `G-${id}` }, room: { id: 10 + id, name: `R${id}` } }))
    vi.mocked(scheduleApi.board).mockImplementation(async (params) => board({ start: params.start, end: params.end }, crowd))
    sessionStorage.setItem('test.board', JSON.stringify({ view: 'week', date: '2026-10-12' }))
    const user = userEvent.setup()
    render()
    const block = await within(await screen.findByTestId('time-grid')).findByRole('button', { name: /4 занятий одновременно, 14:00–15:30/ })
    await user.click(block)
    await waitFor(() => expect(vi.mocked(scheduleApi.board).mock.calls.at(-1)?.[0]).toMatchObject({ start: '2026-10-12', end: '2026-10-12' }))
    expect(within(screen.getByTestId('time-grid')).getAllByRole('button', { name: /G-\d/ })).toHaveLength(4)
  })
})
