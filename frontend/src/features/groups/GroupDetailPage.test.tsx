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
} from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/groups', () => ({
  groupsApi: { get: vi.fn(), list: vi.fn(), schedule: vi.fn(), students: vi.fn() },
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
