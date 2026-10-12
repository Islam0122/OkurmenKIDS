import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupsListPage } from '@/features/groups/GroupsListPage'
import { buildGroup, buildUser, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('@/api/groups', () => ({ groupsApi: { list: vi.fn(), get: vi.fn() } }))

import { groupsApi } from '@/api/groups'

describe('GroupsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'teacher'
  })

  it('renders only the real groups the backend returned for this teacher, with their real stats', async () => {
    vi.mocked(groupsApi.list).mockResolvedValue(
      paginated([buildGroup({ id: 1, name: 'Роботы-1', students_count: 9, max_students: 12 })]),
    )

    renderWithProviders(<GroupsListPage />, { route: '/app/groups' })

    await waitFor(() => expect(screen.getByText('Роботы-1')).toBeInTheDocument())
    expect(screen.getByText('9 / 12')).toBeInTheDocument()
  })

  it('shows an empty state when the teacher has no groups matching the filters', async () => {
    vi.mocked(groupsApi.list).mockResolvedValue(paginated([]))

    renderWithProviders(<GroupsListPage />, { route: '/app/groups' })

    await waitFor(() => expect(screen.getByText('Групп не найдено')).toBeInTheDocument())
  })

  it('offers «Даты старта предметов» to the Team Lead, not to a trainer', async () => {
    vi.mocked(groupsApi.list).mockResolvedValue(paginated([buildGroup()]))
    const { unmount } = renderWithProviders(<GroupsListPage />, { route: '/app/groups' })
    await waitFor(() => expect(screen.getByText('Роботы-1')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Даты старта предметов' })).not.toBeInTheDocument()
    unmount()

    mockRole.role = 'team_lead'
    renderWithProviders(<GroupsListPage />, { route: '/app/groups' })
    expect(await screen.findByRole('button', { name: 'Даты старта предметов' })).toBeInTheDocument()
  })
})
