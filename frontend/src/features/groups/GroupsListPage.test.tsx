import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GroupsListPage } from '@/features/groups/GroupsListPage'
import { buildGroup, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/groups', () => ({ groupsApi: { list: vi.fn(), get: vi.fn() } }))

import { groupsApi } from '@/api/groups'

describe('GroupsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
})
