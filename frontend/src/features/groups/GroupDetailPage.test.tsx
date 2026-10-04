import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import { AxiosError } from 'axios'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupDetailPage } from '@/features/groups/GroupDetailPage'
import {
  buildAnalyticsDashboard,
  buildGroup,
  buildGroupScheduleLesson,
  buildGroupScheduleSlot,
  buildGroupTeacherSummary,
  buildMetric,
  buildUser,
} from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { AcademicConfig } from '@/types/academy'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('@/api/groups', () => ({
  groupsApi: {
    get: vi.fn(), list: vi.fn(), schedule: vi.fn(), students: vi.fn(),
    academicConfig: vi.fn(), createProgram: vi.fn(), saveProgram: vi.fn(), generateLessons: vi.fn(),
  },
}))

vi.mock('@/api/kpi', () => ({
  kpiApi: { dashboard: vi.fn() },
}))

import { groupsApi } from '@/api/groups'
import { kpiApi } from '@/api/kpi'

function renderGroupDetail(id = 1) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/groups/:id" element={<GroupDetailPage />} />
    </Routes>,
    { route: `/app/groups/${id}` },
  )
}

describe('GroupDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'teacher'
  })

  it('shows the group overview by default', async () => {
    vi.mocked(groupsApi.get).mockResolvedValue(
      buildGroup({
        name: 'Роботы-1',
        teachers: [buildGroupTeacherSummary({ schedules: [buildGroupScheduleSlot({ room_name: 'Кабинет 101' })] })],
      }),
    )

    renderGroupDetail(1)

    await waitFor(() => expect(screen.getByText('Роботы-1')).toBeInTheDocument())
    expect(screen.getByText(/Кабинет 101/)).toBeInTheDocument()
  })

  it('groups the schedule tab by weekday, not as a flat lesson list', async () => {
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 1, name: 'Роботы-1' }))
    vi.mocked(groupsApi.schedule).mockResolvedValue({
      group: buildGroup({ id: 1, name: 'Роботы-1' }),
      lessons: [
        buildGroupScheduleLesson({
          id: 5, lesson_number: 5, date: '2026-09-07', weekday: 'mon', weekday_label: 'Понедельник', topic: 'Переменные',
        }),
        buildGroupScheduleLesson({
          id: 6, lesson_number: 6, date: '2026-09-09', weekday: 'wed', weekday_label: 'Среда', topic: 'Условия',
        }),
      ],
    })

    const user = userEvent.setup()
    renderGroupDetail(1)

    await waitFor(() => expect(screen.getByText('Роботы-1')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: 'Расписание' }))

    await waitFor(() => expect(screen.getByText('Понедельник')).toBeInTheDocument())
    expect(screen.getByText('Среда')).toBeInTheDocument()
    expect(screen.getByText('Занятие 5', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Занятие 6', { exact: false })).toBeInTheDocument()
  })

  it('shows KPI data for a period whose lessons are all completed', async () => {
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 5, name: 'Роботы-5' }))
    const base = buildAnalyticsDashboard()
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        lessons: {
          ...base.lessons,
          lessons_total: buildMetric(4),
          lessons_scheduled: buildMetric(0),
          lessons_completed: buildMetric(4),
        },
        attendance: { ...base.attendance, attendance_rate: buildMetric(96.3) },
      }),
    )

    const user = userEvent.setup()
    renderGroupDetail(5)

    await waitFor(() => expect(screen.getByText('Роботы-5')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: 'KPI' }))

    await waitFor(() => expect(screen.getByText('4 (4 проведено)')).toBeInTheDocument())
    expect(screen.getByText('96.3%')).toBeInTheDocument()
    expect(screen.queryByText('Нет данных за выбранный период')).not.toBeInTheDocument()
    expect(kpiApi.dashboard).toHaveBeenCalledWith(expect.objectContaining({ group: 5, period: 'this_month' }))
  })

  it('shows the empty state only when the period has no lessons at all', async () => {
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 5, name: 'Роботы-5' }))
    const base = buildAnalyticsDashboard()
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({ lessons: { ...base.lessons, lessons_total: buildMetric(0), lessons_scheduled: buildMetric(0) } }),
    )

    const user = userEvent.setup()
    renderGroupDetail(5)

    await waitFor(() => expect(screen.getByText('Роботы-5')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: 'KPI' }))

    expect(await screen.findByText('Нет данных за выбранный период')).toBeInTheDocument()
  })
})

function config(overrides: Partial<AcademicConfig> = {}): AcademicConfig {
  return {
    group: { id: 1, name: 'Python PRO — группа 3', course: 'Python PRO', status: 'active' },
    programs: [
      {
        id: 10,
        subject: { id: 1, name: 'Python' },
        teacher: { id: 7, name: 'Иванов Иван' },
        is_active: true,
        has_lessons: false,
        assigned_by: 'Нурлан (Team Lead)',
        assigned_at: '2026-10-04T04:30:00Z',
        slots: [
          { id: 100, day: 'mon', day_label: 'Понедельник', start: '13:00', end: '14:00', room: { id: 1, name: 'Кабинет 101' }, is_active: true },
          { id: 101, day: 'sun', day_label: 'Воскресенье', start: '20:00', end: '21:00', room: { id: 2, name: 'Кабинет 205' }, is_active: true },
        ],
      },
    ],
    subjects: [{ id: 1, name: 'Python' }, { id: 2, name: 'English' }],
    trainers: [
      { id: 7, name: 'Иванов Иван', subjects: ['Python'] },
      { id: 8, name: 'Садыкова Айгуль', subjects: ['Python', 'English'] },
    ],
    rooms: [{ id: 1, name: 'Кабинет 101', capacity: 12 }, { id: 2, name: 'Кабинет 205', capacity: 20 }],
    weekdays: [
      { code: 'mon', label: 'Понедельник' }, { code: 'tue', label: 'Вторник' }, { code: 'wed', label: 'Среда' },
      { code: 'thu', label: 'Четверг' }, { code: 'fri', label: 'Пятница' }, { code: 'sat', label: 'Суббота' },
      { code: 'sun', label: 'Воскресенье' },
    ],
    ...overrides,
  }
}

describe('GroupDetailPage — Team Lead academic configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'team_lead'
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 1, name: 'Python PRO — группа 3' }))
    vi.mocked(groupsApi.schedule).mockResolvedValue({ group: buildGroup({ id: 1 }), lessons: [] })
    vi.mocked(groupsApi.academicConfig).mockResolvedValue(config())
  })

  async function openSchedule() {
    const user = userEvent.setup()
    renderGroupDetail(1)
    await user.click(await screen.findByRole('tab', { name: 'Расписание' }))
    return user
  }

  it('shows the tabs and the configuration summary on «Общая информация»', async () => {
    renderGroupDetail(1)
    for (const name of ['Общая информация', 'Студенты', 'Расписание', 'Сессии', 'Аналитика']) {
      expect(await screen.findByRole('tab', { name })).toBeInTheDocument()
    }
    const summary = await screen.findByTestId('config-summary')
    expect(summary).toHaveTextContent('Иванов Иван')
    expect(summary).toHaveTextContent('Python')
    expect(summary).toHaveTextContent('Пн Вс')
    expect(summary).toHaveTextContent('13:00–14:00, 20:00–21:00')
  })

  it('shows the existing per-day schedule: day, time, room, subject, trainer', async () => {
    await openSchedule()
    const view = await screen.findByTestId('program-view')
    const rows = within(view).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('Понедельник13:00–14:00Кабинет 101PythonИванов Иван')
    expect(rows[2]).toHaveTextContent('Воскресенье20:00–21:00Кабинет 205PythonИванов Иван')
  })

  it('edits: trainer, subject, several weekdays at once with time and room, removes a day, saves', async () => {
    vi.mocked(groupsApi.saveProgram).mockResolvedValue(config())
    const user = await openSchedule()
    await user.click(await screen.findByRole('button', { name: 'Изменить расписание' }))
    const editor = screen.getByTestId('program-editor')

    // Trainer and subject selectors.
    await user.selectOptions(within(editor).getByLabelText('Тренер *'), '8')
    expect(within(editor).getByLabelText('Предмет *')).toHaveValue('1')

    // Remove Sunday, add Wed + Fri 15:00–16:30 in room 101.
    await user.click(within(editor).getByRole('button', { name: 'Удалить Вс 20:00' }))
    await user.click(within(editor).getByRole('button', { name: 'Добавить день' }))
    const panel = within(editor).getByTestId('add-days')
    await user.click(within(panel).getByRole('checkbox', { name: 'Ср' }))
    await user.click(within(panel).getByRole('checkbox', { name: 'Пт' }))
    await user.type(within(panel).getByLabelText('Начало новых дней'), '15:00')
    await user.type(within(panel).getByLabelText('Окончание новых дней'), '16:30')
    await user.selectOptions(within(panel).getByLabelText('Кабинет новых дней'), '1')
    await user.click(within(panel).getByRole('button', { name: 'Добавить' }))
    expect(within(editor).getAllByTestId('slot-row')).toHaveLength(3)

    await user.click(within(editor).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() =>
      expect(groupsApi.saveProgram).toHaveBeenCalledWith(1, 10, {
        teacher: 8,
        subject: 1,
        schedule: [
          { id: 100, day: 'mon', start: '13:00', end: '14:00', room: 1 },
          { day: 'wed', start: '15:00', end: '16:30', room: 1 },
          { day: 'fri', start: '15:00', end: '16:30', room: 1 },
        ],
      }),
    )
  })

  it('validates time on the client and shows backend conflicts', async () => {
    const user = await openSchedule()
    await user.click(await screen.findByRole('button', { name: 'Изменить расписание' }))
    const editor = screen.getByTestId('program-editor')
    const [firstEnd] = within(editor).getAllByLabelText('Окончание')
    await user.clear(firstEnd)
    await user.type(firstEnd, '12:00')
    await user.click(within(editor).getByRole('button', { name: 'Сохранить' }))
    expect(within(editor).getByRole('alert')).toHaveTextContent('Пн: время окончания должно быть позже времени начала.')
    expect(groupsApi.saveProgram).not.toHaveBeenCalled()

    await user.clear(firstEnd)
    await user.type(firstEnd, '14:00')
    vi.mocked(groupsApi.saveProgram).mockRejectedValue(
      new AxiosError('400', '400', undefined, undefined, {
        status: 400, statusText: 'Bad Request', headers: {}, config: {} as never,
        data: { schedule: ['Пн 13:00–14:00: Аудитория «Кабинет 101» уже занята в это время в группе «Frontend-1» (Понедельник 13:30–14:30).'] },
      }),
    )
    await user.click(within(editor).getByRole('button', { name: 'Сохранить' }))
    expect(await within(editor).findByRole('alert')).toHaveTextContent('Аудитория «Кабинет 101» уже занята')
  })

  it('creates the first program for a group without schedule', async () => {
    vi.mocked(groupsApi.academicConfig).mockResolvedValue(config({ programs: [] }))
    vi.mocked(groupsApi.createProgram).mockResolvedValue(config())
    const user = await openSchedule()
    await user.click(await screen.findByRole('button', { name: 'Настроить расписание' }))
    const editor = screen.getByTestId('program-editor')
    await user.selectOptions(within(editor).getByLabelText('Тренер *'), '7')
    await user.selectOptions(within(editor).getByLabelText('Предмет *'), '1')
    const panel = within(editor).getByTestId('add-days')
    for (const day of ['Пн', 'Ср', 'Пт']) await user.click(within(panel).getByRole('checkbox', { name: day }))
    await user.type(within(panel).getByLabelText('Начало новых дней'), '13:00')
    await user.type(within(panel).getByLabelText('Окончание новых дней'), '14:00')
    await user.click(within(panel).getByRole('button', { name: 'Добавить' }))
    await user.click(within(editor).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() =>
      expect(groupsApi.createProgram).toHaveBeenCalledWith(1, {
        teacher: 7,
        subject: 1,
        schedule: [
          { day: 'mon', start: '13:00', end: '14:00', room: null },
          { day: 'wed', start: '13:00', end: '14:00', room: null },
          { day: 'fri', start: '13:00', end: '14:00', room: null },
        ],
      }),
    )
  })

  it('generates lessons with the existing generator', async () => {
    vi.mocked(groupsApi.generateLessons).mockResolvedValue({
      created_count: 8, updated_count: 0, already_existed: 0, expected_total: 8,
      first_date: '2026-10-05', last_date: '2026-10-18', warnings: [], errors: [],
    })
    const user = await openSchedule()
    await user.click(await screen.findByRole('button', { name: 'Сгенерировать занятия' }))
    await waitFor(() => expect(groupsApi.generateLessons).toHaveBeenCalledWith(1))
    expect(await screen.findByText(/Создано занятий: 8/)).toBeInTheDocument()
  })

  it('a Trainer sees the read-only program list, no configuration', async () => {
    mockRole.role = 'teacher'
    renderGroupDetail(1)
    await screen.findByText('Учебные программы')
    expect(screen.queryByRole('tab', { name: 'Сессии' })).not.toBeInTheDocument()
    expect(groupsApi.academicConfig).not.toHaveBeenCalled()
  })
})
