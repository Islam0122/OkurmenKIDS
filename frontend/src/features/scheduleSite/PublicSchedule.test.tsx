import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { PublicLesson, PublicOptions, PublicSchedule } from '@/types/publicSchedule'

import { SiteSchedulePage } from './SchedulePage'

vi.mock('@/api/publicSchedule', () => ({ publicScheduleApi: { options: vi.fn(), lessons: vi.fn() } }))
// The public site must never touch the authenticated client.
vi.mock('@/api/client', async (original) => {
  const actual = await original<typeof import('@/api/client')>()
  const fail = () => { throw new Error('the public site used the authenticated API client') }
  return { ...actual, apiClient: { get: fail, post: fail, put: fail, patch: fail, delete: fail } }
})

import { publicScheduleApi } from '@/api/publicSchedule'

const LONG_GROUP = 'Prog SOFT 1 — вечерняя группа продвинутого уровня'
const FULL_NAME = 'Айжаркын Өмүрбекова-Сыдыкбекова'

function lesson(over: Partial<PublicLesson> = {}): PublicLesson {
  return {
    key: 'lessonkeyaaaa', date: '2026-10-12', start: '14:00', end: '15:30', duration_minutes: 90,
    group: { key: 'groupkeyaaaaa', name: LONG_GROUP }, course: 'Prog SOFT', subject: 'Python',
    status: 'scheduled', status_label: 'Запланирован', rescheduled: false,
    trainer: { key: 'trainerkeyaaa', name: FULL_NAME, color: '#2563EB' }, room: { key: 'roomkeyaaaaaa', name: 'Кабинет 201 (большой)' },
    ...over,
  }
}

const OPTIONS: PublicOptions = {
  today: '2026-10-12', window: { first: '2026-09-11', last: '2027-02-09', max_days: 7 }, hours: { start: '08:00', end: '24:00' },
  show: { trainers: true, rooms: true },
  groups: [{ key: 'groupkeyaaaaa', name: LONG_GROUP, course: 'Prog SOFT' }, { key: 'groupkeybbbbb', name: 'Robo-2', course: 'Robotics' }],
  trainers: [{ key: 'trainerkeyaaa', name: FULL_NAME, color: '#2563EB' }, { key: 'trainerkeybbb', name: 'Бакыт Асанов', color: '#D97706' }],
  rooms: [{ key: 'roomkeyaaaaaa', name: 'Кабинет 201 (большой)' }, { key: 'roomkeybbbbbb', name: 'B2' }],
}

function schedule(start: string, end: string, lessons = [
  lesson(),
  lesson({ key: 'lessonkeybbbb', start: '16:00', end: '17:00', duration_minutes: 60, group: { key: 'groupkeybbbbb', name: 'Robo-2' },
    trainer: { key: 'trainerkeybbb', name: 'Бакыт Асанов', color: '#D97706' }, room: { key: 'roomkeybbbbbb', name: 'B2' },
    status: 'cancelled', status_label: 'Отменён' }),
]): PublicSchedule {
  return { start, end, now: { date: '2026-10-12', time: '11:00', timezone: 'Asia/Bishkek' }, hours: { start: '08:00', end: '24:00' },
    show: { trainers: true, rooms: true }, lessons }
}

function renderSite(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/schedule/day" element={<SiteSchedulePage view="day" />} />
      <Route path="/schedule/week" element={<SiteSchedulePage view="week" />} />
    </Routes>,
    { route },
  )
}

describe('Public schedule site (no login)', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-12T05:00:00Z'))
    vi.mocked(publicScheduleApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(publicScheduleApi.lessons).mockImplementation(async (p) => schedule(p.start, p.end))
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('opens on today, 08:00–24:00, with full group, trainer and room names', async () => {
    renderSite('/schedule/day')
    const grid = await screen.findByTestId('site-grid')
    expect(vi.mocked(publicScheduleApi.lessons).mock.calls[0][0]).toMatchObject({ start: '2026-10-12', end: '2026-10-12' })
    expect(within(grid).getByText('08:00')).toBeInTheDocument()
    expect(within(grid).getByText('24:00')).toBeInTheDocument()
    expect(within(grid).getByText(LONG_GROUP)).toBeInTheDocument()
    expect(within(grid).getByText(FULL_NAME)).toBeInTheDocument()
    expect(within(grid).getAllByText('Кабинет 201 (большой)').length).toBeGreaterThan(0)
    expect(within(grid).getByText('Занятие отменено')).toBeInTheDocument()
    expect(grid.innerHTML).not.toContain('truncate')
  })

  it('filters by group, trainer and room on the server and keeps them across day / week', async () => {
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    await screen.findByTestId('site-grid')
    await user.selectOptions(screen.getByLabelText('Группа'), 'groupkeyaaaaa')
    await user.selectOptions(screen.getByLabelText('Тренер'), 'trainerkeyaaa')
    await user.selectOptions(screen.getByLabelText('Кабинет'), 'roomkeyaaaaaa')
    await waitFor(() => expect(vi.mocked(publicScheduleApi.lessons).mock.calls.at(-1)?.[0]).toMatchObject({
      group: 'groupkeyaaaaa', trainer: 'trainerkeyaaa', room: 'roomkeyaaaaaa',
    }))
    await user.click(screen.getByRole('radio', { name: 'Неделя' }))
    await waitFor(() => expect(vi.mocked(publicScheduleApi.lessons).mock.calls.at(-1)?.[0]).toMatchObject({
      start: '2026-10-12', end: '2026-10-18', group: 'groupkeyaaaaa', trainer: 'trainerkeyaaa', room: 'roomkeyaaaaaa',
    }))
    expect(await screen.findByTestId('site-week')).toBeInTheDocument()
  })

  it('searches a group by name', async () => {
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    const grid = await screen.findByTestId('site-grid')
    await user.type(screen.getByLabelText('Поиск группы'), 'robo')
    await waitFor(() => expect(within(grid).queryByText(LONG_GROUP)).not.toBeInTheDocument())
    expect(within(screen.getByTestId('site-grid')).getByText('Robo-2')).toBeInTheDocument()
  })

  it('shows lesson details with public fields only, no editing', async () => {
    const user = userEvent.setup()
    renderSite('/schedule/day?date=2026-10-12')
    const grid = await screen.findByTestId('site-grid')
    await user.click(within(grid).getByRole('button', { name: new RegExp(LONG_GROUP) }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Prog SOFT')).toBeInTheDocument()
    expect(within(dialog).getByText(FULL_NAME)).toBeInTheDocument()
    for (const label of ['Перенести', 'Отменить', 'Сохранить', 'Удалить', 'Добавить занятие', 'Посещаемость']) {
      expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument()
    }
  })

  it('hides trainers and rooms when the academy does not publish them', async () => {
    vi.mocked(publicScheduleApi.options).mockResolvedValue({ ...OPTIONS, show: { trainers: false, rooms: false }, trainers: [], rooms: [] })
    vi.mocked(publicScheduleApi.lessons).mockImplementation(async (p) => ({
      ...schedule(p.start, p.end, [{ ...lesson(), trainer: undefined, room: undefined }]), show: { trainers: false, rooms: false },
    }))
    renderSite('/schedule/day?date=2026-10-12')
    const grid = await screen.findByTestId('site-grid')
    expect(within(grid).getByText(LONG_GROUP)).toBeInTheDocument()
    expect(screen.queryByLabelText('Тренер')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Кабинет')).not.toBeInTheDocument()
  })

  it('explains a date outside the published window', async () => {
    vi.mocked(publicScheduleApi.lessons).mockRejectedValue({ response: { status: 400, data: { detail: 'Расписание опубликовано с 11.09.2026 по 09.02.2027.' } } })
    renderSite('/schedule/day?date=2025-01-01')
    expect(await screen.findByText(/Расписание опубликовано с/)).toBeInTheDocument()
  })
})
