import { Route, Routes } from 'react-router-dom'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupDetailPage } from '@/features/groups/GroupDetailPage'
import { dynamicsSummary, percentText, scoreText, sortRows } from '@/features/groups/StudentProgress'
import { buildAnalyticsDashboard, buildGroup, buildMetric, buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { GroupStudentProgress, StudentProgressDetail, StudentProgressRow } from '@/types/studentProgress'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: 'teacher' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('@/api/groups', () => ({
  groupsApi: { get: vi.fn(), studentProgress: vi.fn(), studentProgressDetail: vi.fn() },
}))

vi.mock('@/api/kpi', () => ({ kpiApi: { dashboard: vi.fn() } }))

import { groupsApi } from '@/api/groups'
import { kpiApi } from '@/api/kpi'

const NO_CHANGE = { attendance_rate: null, homework_rate: null, average_score: null, test_average: null }

function row(overrides: Partial<StudentProgressRow> = {}): StudentProgressRow {
  return {
    id: 1, name: 'Анна Алиева', first_name: 'Анна', last_name: 'Алиева', status: 'active', status_display: 'Активен',
    in_group_now: true, lessons_held: 10, attendance_marked: 10, attended: 9, late: 1, absences: 1, excused: 0,
    attendance_rate: 90, homework_due: 8, homework_done: 7, homework_rate: 87.5, average_score: 8.5, scored_count: 6,
    tests_count: 0, test_average: null, previous: null, change: NO_CHANGE,
    ...overrides,
  }
}

function progress(students: StudentProgressRow[]): GroupStudentProgress {
  return {
    period: { key: 'this_month', start_date: '2026-10-01', end_date: '2026-10-20' },
    comparison: { start_date: '2026-09-01', end_date: '2026-09-20' },
    lessons_held: 10,
    students,
  }
}

const anna = row({ change: { attendance_rate: 10, homework_rate: -5, average_score: 0.5, test_average: null } })
const bek = row({ id: 2, name: 'Бек Бекова', first_name: 'Бек', attendance_rate: 75, homework_rate: 70, average_score: 7.2, attended: 6, absences: 2 })
const nur = row({ id: 3, name: 'Нур Новая', first_name: 'Нур', lessons_held: 0, attendance_marked: 0, attended: 0, absences: 0,
  attendance_rate: null, homework_due: 0, homework_done: 0, homework_rate: null, average_score: null })

async function openKpi() {
  const user = userEvent.setup()
  renderWithProviders(
    <Routes>
      <Route path="/app/groups/:id" element={<GroupDetailPage />} />
    </Routes>,
    { route: '/app/groups/5' },
  )
  await waitFor(() => expect(screen.getByText('Роботы-5')).toBeInTheDocument())
  await user.click(screen.getByRole('tab', { name: 'KPI' }))
  return user
}

function table() {
  return screen.getByRole('table')
}

describe('«Прогресс студентов» in the group KPI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 5, name: 'Роботы-5' }))
    const base = buildAnalyticsDashboard()
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({ lessons: { ...base.lessons, lessons_total: buildMetric(10), lessons_completed: buildMetric(10) } }),
    )
    vi.mocked(groupsApi.studentProgress).mockResolvedValue(progress([anna, bek, nur]))
  })

  it('shows every student under the group card, with «Нет данных» instead of zeros', async () => {
    await openKpi()
    expect(await screen.findByRole('heading', { name: /Прогресс студентов/ })).toBeInTheDocument()
    expect(screen.getByText('10 (10 проведено)')).toBeInTheDocument() // the group card is still there
    const annaRow = within(table()).getByTestId('progress-row-1')
    expect(within(annaRow).getByText('90%')).toBeInTheDocument()
    expect(within(annaRow).getByText('87,5%')).toBeInTheDocument()
    expect(within(annaRow).getByText('8,5/10')).toBeInTheDocument()
    expect(within(annaRow).getByText('7 из 8')).toBeInTheDocument()
    expect(within(annaRow).getByText(/\+10/)).toBeInTheDocument()
    const nurRow = within(table()).getByTestId('progress-row-3')
    expect(within(nurRow).getAllByText('Нет данных').length).toBeGreaterThanOrEqual(3)
    expect(within(nurRow).queryByText('0%')).not.toBeInTheDocument()
    // Phones get compact cards.
    expect(screen.getByTestId('progress-card-1')).toBeInTheDocument()
  })

  it('asks for the same period as the group KPI and recalculates when it changes', async () => {
    const user = await openKpi()
    await screen.findByRole('heading', { name: /Прогресс студентов/ })
    expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'this_month' }))
    const dashboard = vi.mocked(kpiApi.dashboard).mock.calls.at(-1)?.[0]
    const progressParams = vi.mocked(groupsApi.studentProgress).mock.calls.at(-1)?.[1]
    expect(progressParams?.start_date).toBe(dashboard?.start_date)
    expect(progressParams?.end_date).toBe(dashboard?.end_date)

    await user.click(screen.getByRole('radio', { name: 'Прошлый месяц' }))
    await waitFor(() =>
      expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'last_month' })),
    )
    expect(kpiApi.dashboard).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'last_month' }))
  })

  it('searches by name and sorts by attendance, homework and score', async () => {
    const user = await openKpi()
    await screen.findByRole('heading', { name: /Прогресс студентов/ })
    const names = () => within(table()).getAllByRole('row').slice(1).map((r) => r.querySelector('td p')?.textContent)

    await user.type(screen.getByRole('searchbox', { name: 'Поиск по имени студента' }), 'бек')
    expect(names()).toEqual(['Бек Бекова'])
    await user.clear(screen.getByRole('searchbox', { name: 'Поиск по имени студента' }))

    await user.selectOptions(screen.getByRole('combobox', { name: 'Сортировка' }), 'attendance_rate')
    expect(names()).toEqual(['Анна Алиева', 'Бек Бекова', 'Нур Новая'])
    await user.click(screen.getByRole('button', { name: 'По убыванию' }))
    // Ascending — and a student without data still goes last.
    expect(names()).toEqual(['Бек Бекова', 'Анна Алиева', 'Нур Новая'])
  })

  it('opens a student’s lessons, homework and tests of the period', async () => {
    const detail: StudentProgressDetail = {
      ...progress([]),
      student: anna,
      lessons: [
        {
          id: 41, date: '2026-10-05', lesson_number: 7, topic: 'Циклы', subject: 'Python', attendance: 'absent',
          attendance_display: 'Отсутствовал', homework: [{ id: 9, title: 'Задачи на циклы', status: 'checked', status_display: 'Проверено', score: 9 }],
        },
        { id: 42, date: '2026-10-08', lesson_number: 8, topic: 'Функции', subject: 'Python', attendance: null, attendance_display: null, homework: [] },
      ],
      tests: [{ id: 'a', title: 'Python Basics', date: '2026-10-10', score: 80, passed: true }],
    }
    vi.mocked(groupsApi.studentProgressDetail).mockResolvedValue(detail)
    const user = await openKpi()
    await screen.findByRole('heading', { name: /Прогресс студентов/ })

    await user.click(within(table()).getByTestId('progress-row-1'))
    const panel = await within(table()).findByTestId('progress-detail-1')
    expect(groupsApi.studentProgressDetail).toHaveBeenCalledWith(5, 1, expect.objectContaining({ period: 'this_month' }))
    expect(await within(panel).findByText('Циклы')).toBeInTheDocument()
    expect(within(panel).getByText('Отсутствовал')).toBeInTheDocument()
    expect(within(panel).getByText('ДЗ: Задачи на циклы')).toBeInTheDocument()
    expect(within(panel).getByText('9/10')).toBeInTheDocument()
    expect(within(panel).getByText('Не отмечено')).toBeInTheDocument()
    expect(within(panel).getByText('ДЗ не задавалось')).toBeInTheDocument()
    expect(within(panel).getByText('Python Basics')).toBeInTheDocument()
    expect(within(panel).getByText(/посещаемость выросла на 10 п\.п\./)).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'Карточка студента' })).toHaveAttribute('href', '/app/students/1')
  })

  it('shows an empty state when the group had no students in the period', async () => {
    vi.mocked(groupsApi.studentProgress).mockResolvedValue(progress([]))
    await openKpi()
    expect(await screen.findByText('В этот период в группе не было студентов')).toBeInTheDocument()
  })
})

describe('manual «С — По» range', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 5, name: 'Роботы-5' }))
    const base = buildAnalyticsDashboard()
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({ lessons: { ...base.lessons, lessons_total: buildMetric(10), lessons_completed: buildMetric(10) } }),
    )
    vi.mocked(groupsApi.studentProgress).mockResolvedValue(progress([anna, bek, nur]))
  })

  const from = () => screen.getByLabelText('Дата начала')
  const to = () => screen.getByLabelText('Дата окончания')
  const names = () => within(screen.getByRole('table')).getAllByRole('row').slice(1).map((r) => r.querySelector('td p')?.textContent)

  it('applies the range to the group KPI and the students, keeping search and sorting', async () => {
    const user = await openKpi()
    await screen.findByRole('heading', { name: /Прогресс студентов/ })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Сортировка' }), 'attendance_rate')
    await user.type(screen.getByRole('searchbox', { name: 'Поиск по имени студента' }), 'а')

    fireEvent.change(from(), { target: { value: '2026-10-01' } })
    fireEvent.change(to(), { target: { value: '2026-10-10' } })
    await user.click(screen.getByRole('button', { name: 'Применить' }))

    await waitFor(() =>
      expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, { period: 'custom', start_date: '2026-10-01', end_date: '2026-10-10' }),
    )
    expect(kpiApi.dashboard).toHaveBeenLastCalledWith(
      expect.objectContaining({ period: 'custom', start_date: '2026-10-01', end_date: '2026-10-10', group: 5 }),
    )
    expect(await screen.findByTestId('progress-range')).toHaveTextContent('01.10.2026 — 10.10.2026')
    // The search and the sorting are still there.
    expect(screen.getByRole('searchbox', { name: 'Поиск по имени студента' })).toHaveValue('а')
    expect(screen.getByRole('combobox', { name: 'Сортировка' })).toHaveValue('attendance_rate')
    await waitFor(() => expect(names()).toEqual(['Анна Алиева', 'Бек Бекова', 'Нур Новая']))
    expect(from()).toHaveValue('2026-10-01')
    // No quick period is highlighted while the manual range is on.
    expect(screen.getByRole('radio', { name: 'Этот месяц' })).toHaveAttribute('aria-checked', 'false')
  })

  it('refuses a start date after the end date', async () => {
    const user = await openKpi()
    await screen.findByRole('heading', { name: /Прогресс студентов/ })
    const calls = vi.mocked(groupsApi.studentProgress).mock.calls.length
    fireEvent.change(from(), { target: { value: '2026-10-10' } })
    fireEvent.change(to(), { target: { value: '2026-10-01' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Дата начала не может быть позже даты окончания.')
    const apply = screen.getByRole('button', { name: 'Применить' })
    expect(apply).toBeDisabled()
    await user.click(apply)
    expect(groupsApi.studentProgress).toHaveBeenCalledTimes(calls)
  })

  it('«Сбросить» and the quick periods go back to the standard period', async () => {
    const user = await openKpi()
    await screen.findByRole('heading', { name: /Прогресс студентов/ })
    expect(screen.getByRole('button', { name: 'Сбросить' })).toBeDisabled()
    fireEvent.change(from(), { target: { value: '2026-10-01' } })
    fireEvent.change(to(), { target: { value: '2026-10-10' } })
    await user.click(screen.getByRole('button', { name: 'Применить' }))
    await waitFor(() => expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'custom' })))

    await user.click(screen.getByRole('button', { name: 'Сбросить' }))
    await waitFor(() => expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'this_month' })))
    expect(screen.getByRole('radio', { name: 'Этот месяц' })).toHaveAttribute('aria-checked', 'true')

    fireEvent.change(from(), { target: { value: '2026-10-02' } })
    await user.click(screen.getByRole('button', { name: 'Применить' }))
    await waitFor(() => expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'custom', start_date: '2026-10-02' })))
    await user.click(screen.getByRole('radio', { name: 'Последние 7 дней' }))
    await waitFor(() => expect(groupsApi.studentProgress).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'last_7_days' })))
    expect(kpiApi.dashboard).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'last_7_days' }))
  })

  it('says «Нет данных за выбранный период» when the range has nothing', async () => {
    vi.mocked(groupsApi.studentProgress).mockResolvedValue({ ...progress([nur]), lessons_held: 0 })
    await openKpi()
    const section = (await screen.findByRole('heading', { name: /Прогресс студентов/ })).closest('section') as HTMLElement
    expect(await within(section).findByText('Нет данных за выбранный период')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    // The filters stay, so another range can be picked.
    expect(screen.getByLabelText('Дата начала')).toBeInTheDocument()
  })
})

describe('student progress helpers', () => {
  it('never shows a missing value as zero', () => {
    expect(percentText(null)).toBe('Нет данных')
    expect(scoreText(null)).toBe('Нет данных')
    expect(percentText(0)).toBe('0%')
    expect(scoreText(7.25)).toBe('7,3/10')
  })

  it('sorts students without data last in both directions', () => {
    const order = (descending: boolean) => sortRows([nur, bek, anna], 'average_score', descending).map((r) => r.id)
    expect(order(true)).toEqual([1, 2, 3])
    expect(order(false)).toEqual([2, 1, 3])
  })

  it('summarises the dynamics, or says there is not enough data', () => {
    expect(dynamicsSummary(nur)).toBe('Недостаточно данных для сравнения с прошлым периодом.')
    expect(dynamicsSummary(anna)).toBe(
      'По сравнению с прошлым периодом посещаемость выросла на 10 п.п., доля выполненных ДЗ снизилась на 5 п.п., средний балл вырос на 0,5.',
    )
  })
})
