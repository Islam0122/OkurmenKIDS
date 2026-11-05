import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { MonthlyPerformance, PerformanceDay } from '@/api/monthlyPerformance'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/monthlyPerformance', () => ({
  monthlyPerformanceApi: { month: vi.fn(), correct: vi.fn() },
}))

const auth = { status: 'authenticated' as string, login: vi.fn() }
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: auth.status === 'authenticated' ? { id: 1, role: 'teacher' } : null, status: auth.status, login: auth.login, logout: vi.fn() }),
}))

import { monthlyPerformanceApi } from '@/api/monthlyPerformance'

import { dashboardKeyStorage } from './dashboardKey'
import { MonthlyPerformanceSite, REFRESH_INTERVAL_MS } from './MonthlyPerformanceSite'
import { niceMax } from './PerformanceChart'

const api = vi.mocked(monthlyPerformanceApi)

function day(n: number, extra: Partial<PerformanceDay> = {}): PerformanceDay {
  const future = n > 5
  return {
    date: `2026-11-${String(n).padStart(2, '0')}`, day: n, weekday: ((n + 6) % 7) + 1, is_today: n === 5, is_future: future,
    attendance_percent: null, attendance_marked: 0, attendance_attended: 0,
    homework_percent: null, homework_results: 0, homework_done: 0, lessons_count: 0,
    active_groups: null, active_students: null,
    status: future ? 'future' : n === 5 ? 'live' : 'final', manual_fields: [], manual_comment: '', computed_at: null,
    ...extra,
  }
}

function series(days: PerformanceDay[], field: 'attendance_percent' | 'homework_percent' | 'active_groups' | 'active_students') {
  return days.filter((d) => !d.is_future).map((d) => ({ date: d.date, day: d.day, value: d[field] }))
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
      attendance: { points: series(days, 'attendance_percent'), average: 82.5 },
      homework: { points: series(days, 'homework_percent'), average: 91.3 },
      groups: { points: series(days, 'active_groups'), average: 4 },
      students: { points: series(days, 'active_students'), average: 41 },
    },
    available_years: [2026, 2025],
    can_edit: false,
    access: { mode: 'user', name: 'Айгуль' },
    ...overrides,
  }
}

function emptyPayload(): MonthlyPerformance {
  const days = Array.from({ length: 31 }, (_, i) => ({ ...day(i + 1), date: `2026-10-${String(i + 1).padStart(2, '0')}`, is_future: false, is_today: false, status: 'missing' as const }))
  const empty = { value: null, date: null, previous_value: null, previous_date: null, change: null }
  const none = { points: days.map((d) => ({ date: d.date, day: d.day, value: null })), average: null }
  return {
    ...payload(), month: 10, month_label: 'Октябрь', is_current_month: false, days,
    summary: { attendance_percent: { ...empty, month_average: null }, homework_percent: { ...empty, month_average: null }, active_groups: empty, active_students: empty },
    trends: { attendance: none, homework: none, groups: none, students: none },
  }
}

function unauthorized() {
  return new AxiosError('401', 'ERR_BAD_REQUEST', undefined, undefined, { status: 401, data: {} } as AxiosResponse)
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

function renderSite(route = '/monthly-performance?year=2026&month=11') {
  return renderWithProviders(
    <Routes>
      <Route path="/monthly-performance" element={<><MonthlyPerformanceSite /><LocationProbe /></>} />
    </Routes>,
    { route },
  )
}

beforeEach(() => {
  auth.status = 'authenticated'
  auth.login.mockReset()
  dashboardKeyStorage.clear()
  api.month.mockReset()
  api.correct.mockReset()
  api.month.mockResolvedValue(payload())
})

afterEach(() => {
  vi.useRealTimers()
})

describe('сайт «Общая статистика»', () => {
  it('отдельная страница: своя шапка, карточки, таблица и четыре графика — без меню LMS', async () => {
    renderSite()
    expect(await screen.findByText('92,5%')).toBeInTheDocument()
    expect(api.month).toHaveBeenCalledWith({ year: 2026, month: 11 }, null)
    expect(screen.getByText('OKURMENKIDS')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Общая статистика академии' })).toBeInTheDocument()
    expect(screen.getByText('Ноябрь 2026')).toBeInTheDocument()
    expect(screen.getByTestId('clock')).toHaveTextContent(/\d{2}:\d{2}/)
    for (const name of ['Выбрать месяц', 'Обновить данные', 'Полноэкранный режим', 'Режим телевизора']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    // Не кабинет LMS: ни бокового меню, ни ссылок кабинета.
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.queryByText('Сегодня')).not.toBeInTheDocument()

    for (const label of ['Посещаемость', 'Выполнение домашних заданий', 'Активные группы', 'Активные студенты']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    expect(screen.getByText('Изменение за день: +5 п.п.')).toBeInTheDocument()
    expect(screen.getByText('Изменение за день: +2')).toBeInTheDocument()

    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader')).toHaveLength(31) // «Ноябрь» + 30 дней
    expect(within(table).getByRole('columnheader', { name: '5' })).toHaveAttribute('aria-current', 'date')
    for (const label of ['Посещаемость (%)', 'Домашние задания (%)', 'Количество групп', 'Количество студентов']) {
      expect(within(table).getByRole('rowheader', { name: label })).toBeInTheDocument()
    }
    // Прошедшие дни без данных выделены и подписаны «—», а не 0.
    const attendance = within(table).getByRole('row', { name: /Посещаемость/ })
    expect(attendance.querySelectorAll('td[data-missing]').length).toBe(3)
    expect(within(table).queryByTitle('Скорректировать показатели')).not.toBeInTheDocument()

    for (const title of ['График посещаемости', 'Выполнение домашних заданий', 'Динамика количества студентов', 'Динамика количества групп']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument()
    }
  })

  it('без входа — экран доступа; ключ открывает статистику и запоминается', async () => {
    auth.status = 'guest'
    const user = userEvent.setup()
    renderSite()
    expect(await screen.findByText('Доступ только для сотрудников академии.')).toBeInTheDocument()
    expect(api.month).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('Ключ доступа'), 'okd_secret')
    await user.click(screen.getByRole('button', { name: 'Открыть по ключу' }))
    expect(await screen.findByText('92,5%')).toBeInTheDocument()
    expect(api.month).toHaveBeenCalledWith({ year: 2026, month: 11 }, 'okd_secret')
    expect(dashboardKeyStorage.get()).toBe('okd_secret')
  })

  it('ключ из ссылки ?key=… запоминается и убирается из адреса', async () => {
    auth.status = 'guest'
    renderSite('/monthly-performance?key=okd_tv&tv=1')
    await screen.findByTestId('tv-mode')
    await waitFor(() => expect(screen.getByTestId('location')).not.toHaveTextContent('key='))
    expect(screen.getByTestId('location')).toHaveTextContent('tv=1')
    expect(dashboardKeyStorage.get()).toBe('okd_tv')
    await waitFor(() => expect(api.month).toHaveBeenCalledWith(expect.any(Object), 'okd_tv'))
  })

  it('отключённый ключ — снова экран доступа с объяснением', async () => {
    auth.status = 'guest'
    dashboardKeyStorage.set('okd_old')
    api.month.mockRejectedValue(unauthorized())
    renderSite()
    expect(await screen.findByText(/Ключ доступа недействителен или отключён/)).toBeInTheDocument()
  })

  it('вход сотрудника с экрана доступа', async () => {
    auth.status = 'guest'
    auth.login.mockResolvedValue({ id: 1 })
    const user = userEvent.setup()
    renderSite()
    await user.type(await screen.findByLabelText('Логин'), 'aigul')
    await user.type(screen.getByLabelText('Пароль'), 'secret')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    expect(auth.login).toHaveBeenCalledWith('aigul', 'secret')
  })

  it('пустой месяц — «нет данных», а не нули', async () => {
    api.month.mockResolvedValue(emptyPayload())
    renderSite('/monthly-performance?year=2026&month=10')
    expect(await screen.findAllByText('Нет данных за этот месяц')).toHaveLength(4)
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
    expect(screen.getAllByText('Нет данных для сравнения')).toHaveLength(4)
  })

  it('выбор месяца и обновление данных', async () => {
    const user = userEvent.setup()
    renderSite()
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Выбрать месяц' }))
    api.month.mockResolvedValue(emptyPayload())
    await user.selectOptions(screen.getByLabelText('Месяц'), '10')
    await waitFor(() => expect(api.month).toHaveBeenLastCalledWith({ year: 2026, month: 10 }, null))
    await user.selectOptions(screen.getByLabelText('Год'), '2025')
    await waitFor(() => expect(api.month).toHaveBeenLastCalledWith({ year: 2025, month: 10 }, null))
    const calls = api.month.mock.calls.length
    await user.click(screen.getByRole('button', { name: 'Обновить данные' }))
    await waitFor(() => expect(api.month.mock.calls.length).toBe(calls + 1))
    await user.click(screen.getByRole('button', { name: 'Текущий месяц' }))
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/monthly-performance$/)
  })

  it('режим телевизора: весь экран, без кнопок, часы, выход по Esc', async () => {
    const user = userEvent.setup()
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    document.documentElement.requestFullscreen = requestFullscreen
    renderSite()
    await user.click(await screen.findByRole('button', { name: 'Режим телевизора' }))
    expect(screen.getByTestId('tv-mode')).toBeInTheDocument()
    expect(requestFullscreen).toHaveBeenCalled()
    expect(screen.getByTestId('clock')).toHaveTextContent(/\d{2}:\d{2}/)
    expect(screen.queryByRole('button', { name: 'Выбрать месяц' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Обновить данные' })).not.toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('tv=1')
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('tv-mode')).not.toBeInTheDocument())
  })

  it('автоматически обновляет данные каждые 5 минут', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderSite('/monthly-performance?tv=1')
    await screen.findByTestId('tv-mode')
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
    renderSite()
    const table = await screen.findByRole('table')
    await user.click(within(table).getAllByTitle('Скорректировать показатели')[3])
    const dialog = await screen.findByRole('dialog', { name: 'Корректировка за 4 ноября' })
    const groups = within(dialog).getByLabelText('Количество групп')
    await user.clear(groups)
    await user.type(groups, '5')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.correct).toHaveBeenCalledWith('2026-11-04', { comment: '', active_groups: 5 }))
  })

  it('шкала количества — «круглый» максимум', () => {
    expect(niceMax(42)).toBe(80)
    expect(niceMax(4)).toBe(8)
    expect(niceMax(0)).toBe(4)
    expect(niceMax(310)).toBe(400)
  })
})
