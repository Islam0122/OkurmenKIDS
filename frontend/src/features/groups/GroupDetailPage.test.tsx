import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupDetailPage } from '@/features/groups/GroupDetailPage'
import { buildGroup, buildGroupScheduleLesson } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/groups', () => ({
  groupsApi: { get: vi.fn(), list: vi.fn(), schedule: vi.fn(), students: vi.fn() },
}))

import { groupsApi } from '@/api/groups'

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
    vi.mocked(groupsApi.get).mockResolvedValue(buildGroup({ name: 'Роботы-1', room_name: 'Кабинет 101' }))

    renderGroupDetail(1)

    await waitFor(() => expect(screen.getByText('Роботы-1')).toBeInTheDocument())
    expect(screen.getByText('Кабинет 101')).toBeInTheDocument()
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
    await user.click(screen.getByRole('button', { name: 'Расписание' }))

    await waitFor(() => expect(screen.getByText('Понедельник')).toBeInTheDocument())
    expect(screen.getByText('Среда')).toBeInTheDocument()
    expect(screen.getByText('Занятие 5', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Занятие 6', { exact: false })).toBeInTheDocument()
  })
})
