import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { MonthlyPerformance, PerformanceDay } from '@/api/monthlyPerformance'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/monthlyPerformance', () => ({
  monthlyPerformanceApi: { month: vi.fn(), correct: vi.fn() },
}))

const auth = { role: 'accountant' }
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: auth.role, first_name: 'Айгуль' }, status: 'authenticated', logout: vi.fn() }),
}))

import { monthlyPerformanceApi } from '@/api/monthlyPerformance'

import { MonthlyPerformancePage, REFRESH_INTERVAL_MS } from './MonthlyPerformancePage'

const api = vi.mocked(monthlyPerformanceApi)

function day(n: number, extra: Partial<PerformanceDay> = {}): PerformanceDay {
  const date = `2026-11-${String(n).padStart(2, '0')}`
  const future = n > 5
  return {
    date, day: n, weekday: ((n + 6) % 7) + 1, is_today: n === 5, is_future: future,
    attendance_percent: null, attendance_marked: 0, attendance_attended: 0,
    homework_percent: null, homework_results: 0, homework_done: 0, lessons_count: 0,
    active_groups: null, active_students: null,
    status: future ? 'future' : n === 5 ? 'live' : 'final', manual_fields: [], manual_comment: '', computed_at: null,
    ...extra,
  }
}

function payload(overrides: Partial<MonthlyPerformance> = {}): MonthlyPerformance {
  const days = Array.from({ length: 30 }, (_, i) => day(i + 1))
  days[3] = day(4, { attendance_percent: 80, homework_percent: 90, active_groups: 4, active_students: 40 })
  days[4] = day(5, { attendance_percent: 85, homework_percent: 92.5, active_groups: 4, active_students: 42, manual_fields: ['active_students'] })
  return {
    year: 2026, month: 11, month_label: 'Ноябрь', today: '2026-11-05', is_current_month: true,
    generated_at: '2026-11-05T10:00:00+06:00', timezone: 'Asia/Bishkek', days,
    summary: {
      attendance_percent: { value: 85, date: '2026-11-05', previous_value: 80, previous_date: '2026-11-04', change: 5, month_average: 82.5 },
      homework_percent: { value: 92.5, date: '2026-11-05', previous_value: 90, previous_date: '2026-11-04', change: 2.5, month_average: 91.2 },
      active_groups: { value: 4, date: '2026-11-05', previous_value: 4, previous_date: '2026-11-04', change: 0 },
      active_students: { value: 42, date: '2026-11-05', previous_value: 40, previous_date: '2026-11-04', change: 2 },
    },
    trends: {
      attendance: { points: days.slice(0, 5).map((d) => ({ date: d.date, day: d.day, value: d.attendance_percent })), average: 82.5 },
      homework: { points: days.slice(0, 5).map((d) => ({ date: d.date, day: d.day, value: d.homework_percent })), average: 91.3 },
    },
    available_years: [2026, 2025],
    can_edit: false,
    ...overrides,
  }
}

function emptyPayload(): MonthlyPerformance {
  const days = Array.from({ length: 31 }, (_, i) => ({ ...day(i + 1), date: `2026-10-${String(i + 1).padStart(2, '0')}`, is_future: false, is_today: false, status: 'missing' as const }))
  const empty = { value: null, date: null, previous_value: null, previous_date: null, change: null }
  return {
    ...payload(), month: 10, month_label: 'Октябрь', is_current_month: false, days,
    summary: { attendance_percent: { ...empty, month_average: null }, homework_percent: { ...empty, month_average: null }, active_groups: empty, active_students: empty },
    trends: { attendance: { points: days.map((d) => ({ date: d.date, day: d.day, value: null })), average: null }, homework: { points: [], average: null } },
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

function renderPage(route = '/dashboard/monthly-performance?year=2026&month=11') {
  return renderWithProviders(
    <Routes>
      <Route path="/dashboard/monthly-performance" element={<><MonthlyPerformancePage /><LocationProbe /></>} />
    </Routes>,
    { route },
  )
}

beforeEach(() => {
  auth.role = 'accountant'
  api.month.mockReset()
  api.correct.mockReset()
  api.month.mockResolvedValue(payload())
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Общая статистика', () => {
  it('показывает карточки, изменение за день и таблицу по всем дням месяца', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Общая статистика' })).toBeInTheDocument()
    expect(api.month).toHaveBeenCalledWith({ year: 2026, month: 11 })
    expect(await screen.findByText('92,5%')).toBeInTheDocument()
    expect(screen.getByText('Изменение за день: +5 п.п.')).toBeInTheDocument()
    expect(screen.getByText('Изменение за день: +2')).toBeInTheDocument()
    expect(screen.getByText('Изменение за день: 0')).toBeInTheDocument()

    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader')).toHaveLength(31) // «Ноябрь» + 30 дней
    const attendanceRow = within(table).getByRole('row', { name: /Посещаемость/ })
    expect(within(attendanceRow).getByText('85%')).toBeInTheDocument()
    expect(within(attendanceRow).getAllByText('—').length).toBeGreaterThan(0) // дни без занятий — не 0
    for (const label of ['Домашние задания', 'Количество групп', 'Количество студентов']) {
      expect(within(table).getByRole('rowheader', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByText('Динамика за месяц')).toBeInTheDocument()
    expect(screen.getByText(/Последнее обновление/)).toBeInTheDocument()
    // Сотрудник без права — без кнопок корректировки.
    expect(within(table).queryByTitle('Скорректировать показатели')).not.toBeInTheDocument()
    // Бухгалтер — простая шапка с возвратом в свой кабинет.
    expect(screen.getByRole('link', { name: 'В свой кабинет' })).toHaveAttribute('href', '/accounting')
  })

  it('пустой месяц — «нет данных», а не нули', async () => {
    api.month.mockResolvedValue(emptyPayload())
    renderPage('/dashboard/monthly-performance?year=2026&month=10')
    expect(await screen.findAllByText('Нет данных за этот месяц')).toHaveLength(2)
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
    expect(screen.getAllByText('Изменение за день: —')).toHaveLength(4)
  })

  it('выбор месяца и года перезагружает данные', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('table')
    api.month.mockResolvedValue(emptyPayload())
    await user.selectOptions(screen.getByLabelText('Месяц'), '10')
    await waitFor(() => expect(api.month).toHaveBeenLastCalledWith({ year: 2026, month: 10 }))
    await user.selectOptions(screen.getByLabelText('Год'), '2025')
    await waitFor(() => expect(api.month).toHaveBeenLastCalledWith({ year: 2025, month: 10 }))
    await user.click(screen.getByRole('button', { name: 'Текущий месяц' }))
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/dashboard\/monthly-performance$/)
  })

  it('режим телевизора: на весь экран, часы, выход по Esc', async () => {
    const user = userEvent.setup()
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    document.documentElement.requestFullscreen = requestFullscreen
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Режим телевизора' }))
    expect(screen.getByTestId('tv-mode')).toBeInTheDocument()
    expect(requestFullscreen).toHaveBeenCalled()
    expect(screen.getByTestId('tv-clock')).toHaveTextContent(/\d{2}:\d{2}/)
    expect(screen.queryByLabelText('Месяц')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'В свой кабинет' })).not.toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('tv=1')
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('tv-mode')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Режим телевизора' })).toBeInTheDocument()
  })

  it('автоматически обновляет данные каждые 5 минут', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderPage('/dashboard/monthly-performance?year=2026&month=11&tv=1')
    await screen.findByTestId('tv-clock')
    await waitFor(() => expect(api.month).toHaveBeenCalledTimes(1))
    await act(async () => {
      vi.advanceTimersByTime(REFRESH_INTERVAL_MS + 100)
    })
    await waitFor(() => expect(api.month).toHaveBeenCalledTimes(2))
  })

  it('сотрудник с правом корректирует показатели дня', async () => {
    const user = userEvent.setup()
    api.month.mockResolvedValue(payload({ can_edit: true }))
    api.correct.mockResolvedValue({})
    renderPage()
    const table = await screen.findByRole('table')
    await user.click(within(table).getAllByTitle('Скорректировать показатели')[3])
    const dialog = await screen.findByRole('dialog', { name: 'Корректировка за 4 ноября' })
    const groups = within(dialog).getByLabelText('Количество групп')
    await user.clear(groups)
    await user.type(groups, '5')
    await user.type(within(dialog).getByLabelText('Комментарий'), 'Сверка')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.correct).toHaveBeenCalledWith('2026-11-04', { comment: 'Сверка', active_groups: 5 }))
  })
})
