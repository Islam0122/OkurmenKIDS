import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SchedulePage } from '@/features/schedule/SchedulePage'
import { buildGroup, buildLesson, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/lessons', () => ({ lessonsApi: { list: vi.fn() } }))
vi.mock('@/api/rooms', () => ({ roomsApi: { list: vi.fn() } }))
vi.mock('@/api/subjects', () => ({ subjectsApi: { list: vi.fn() } }))
vi.mock('@/hooks/useGroups', () => ({ useGroups: () => ({ data: paginated([buildGroup()]) }) }))

import { lessonsApi } from '@/api/lessons'
import { roomsApi } from '@/api/rooms'
import { subjectsApi } from '@/api/subjects'

describe('SchedulePage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-10T10:00:00Z'))
    vi.mocked(roomsApi.list).mockResolvedValue(paginated([]))
    vi.mocked(subjectsApi.list).mockResolvedValue(paginated([]))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('renders the current week and places each real lesson under its own day', async () => {
    const lesson = buildLesson({ id: 7, date: '2026-09-10', subject_name: 'Робототехника', group_name: 'Роботы-1' })
    vi.mocked(lessonsApi.list).mockResolvedValue(paginated([lesson]))

    renderWithProviders(<SchedulePage />, { route: '/app/schedule' })

    await waitFor(() => expect(screen.getByText('Робототехника')).toBeInTheDocument())
    expect(screen.getAllByText('Роботы-1').length).toBeGreaterThan(0)
  })

  it('switches to the day view and re-fetches only that day’s lessons', async () => {
    vi.mocked(lessonsApi.list).mockResolvedValue(paginated([]))
    const user = userEvent.setup()

    renderWithProviders(<SchedulePage />, { route: '/app/schedule' })
    await waitFor(() => expect(lessonsApi.list).toHaveBeenCalled())

    await user.click(screen.getByRole('button', { name: 'День' }))

    await waitFor(() => {
      const lastCall = vi.mocked(lessonsApi.list).mock.calls.at(-1)?.[0]
      expect(lastCall?.date_from).toBe(lastCall?.date_to)
    })
  })
})
