import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
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
import type { TrainerAssignmentOverview } from '@/types/academy'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('@/api/groups', () => ({
  groupsApi: {
    get: vi.fn(), list: vi.fn(), schedule: vi.fn(), students: vi.fn(), trainerAssignments: vi.fn(), assignTrainer: vi.fn(),
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

function overview(overrides: Partial<TrainerAssignmentOverview> = {}): TrainerAssignmentOverview {
  return {
    group: { id: 1, name: 'Python PRO — группа 3', course: 'Python PRO' },
    programs: [
      { id: 10, subject: { id: 1, name: 'Python' }, teacher: { id: 7, name: 'Иванов Иван' }, is_active: true,
        assigned_by: 'Нурлан (Team Lead)', assigned_at: '2026-10-04T04:30:00Z' },
    ],
    subjects: [{ id: 1, name: 'Python' }, { id: 2, name: 'English' }],
    trainers: [
      { id: 7, name: 'Иванов Иван', subjects: ['Python'] },
      { id: 8, name: 'Садыкова Айгуль', subjects: ['Python', 'English'] },
    ],
    ...overrides,
  }
}

describe('GroupDetailPage — Team Lead assigns trainers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'team_lead'
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ id: 1, name: 'Python PRO — группа 3' }))
  })

  it('shows the group trainer, who assigned it and when', async () => {
    vi.mocked(groupsApi.trainerAssignments).mockResolvedValue(overview())
    renderGroupDetail(1)
    const row = await screen.findByTestId('trainer-program')
    expect(row).toHaveTextContent('Предмет: Python')
    expect(row).toHaveTextContent('Иванов Иван')
    expect(row).toHaveTextContent('Назначил: Нурлан (Team Lead)')
    expect(row).toHaveTextContent('Дата назначения: 04.10.2026')
    expect(screen.getByRole('link', { name: 'Иванов Иван' })).toHaveAttribute('href', '/app/trainers/7')
    expect(screen.getByRole('button', { name: 'Изменить тренера' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Назначить тренера' })).toBeInTheDocument()
  })

  it('replaces the trainer only after a confirmation', async () => {
    vi.mocked(groupsApi.trainerAssignments).mockResolvedValue(overview())
    vi.mocked(groupsApi.assignTrainer).mockResolvedValue(
      overview({
        programs: [{ ...overview().programs[0], teacher: { id: 8, name: 'Садыкова Айгуль' } }],
        result: { program: 10, created: false, previous_teacher: 'Иванов Иван', teacher: 'Садыкова Айгуль', lessons_reassigned: 3 },
      }),
    )
    const user = userEvent.setup()
    renderGroupDetail(1)
    await user.click(await screen.findByRole('button', { name: 'Изменить тренера' }))
    await user.selectOptions(screen.getByLabelText('Тренер *'), '8')
    await user.click(screen.getByRole('button', { name: 'Изменить' }))

    const confirm = await screen.findByTestId('confirm-change')
    expect(confirm).toHaveTextContent('Сейчас: Иванов Иван')
    expect(confirm).toHaveTextContent('Новый: Садыкова Айгуль')
    expect(groupsApi.assignTrainer).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Подтвердить' }))
    await waitFor(() => expect(groupsApi.assignTrainer).toHaveBeenCalledWith(1, { teacher: 8, program: 10 }))
  })

  it('assigns a trainer to a subject without one', async () => {
    vi.mocked(groupsApi.trainerAssignments).mockResolvedValue(overview())
    vi.mocked(groupsApi.assignTrainer).mockResolvedValue(overview())
    const user = userEvent.setup()
    renderGroupDetail(1)
    await user.click(await screen.findByRole('button', { name: 'Назначить тренера' }))
    await user.selectOptions(screen.getByLabelText('Предмет *'), '2')
    await user.selectOptions(screen.getByLabelText('Тренер *'), '8')
    await user.click(screen.getByRole('button', { name: 'Назначить' }))
    await waitFor(() => expect(groupsApi.assignTrainer).toHaveBeenCalledWith(1, { teacher: 8, subject: 2 }))
  })

  it('does not re-assign the same trainer', async () => {
    vi.mocked(groupsApi.trainerAssignments).mockResolvedValue(overview())
    const user = userEvent.setup()
    renderGroupDetail(1)
    await user.click(await screen.findByRole('button', { name: 'Изменить тренера' }))
    await user.selectOptions(screen.getByLabelText('Тренер *'), '7')
    await user.click(screen.getByRole('button', { name: 'Изменить' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Этот тренер уже назначен.')
    expect(groupsApi.assignTrainer).not.toHaveBeenCalled()
  })

  it('a Trainer sees the read-only program list, no assignment', async () => {
    mockRole.role = 'teacher'
    renderGroupDetail(1)
    await screen.findByText('Учебные программы')
    expect(screen.queryByRole('button', { name: 'Назначить тренера' })).not.toBeInTheDocument()
    expect(groupsApi.trainerAssignments).not.toHaveBeenCalled()
  })
})
