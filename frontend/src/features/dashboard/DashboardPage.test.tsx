import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { buildLesson, buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ first_name: 'Айгуль' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

const mockUseDashboardData = vi.fn()
vi.mock('@/features/dashboard/useDashboardData', () => ({
  useDashboardData: () => mockUseDashboardData(),
  todayISO: () => '2026-09-10',
}))

describe('DashboardPage', () => {
  it('greets the teacher by first name and renders today’s real lessons', () => {
    const lesson = buildLesson({ id: 42, subject_name: 'Робототехника', group_name: 'Роботы-1', start_time: '15:00:00' })
    mockUseDashboardData.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: {
        today: '2026-09-10',
        lessonsToday: [lesson],
        nextLesson: lesson,
        studentsToday: 8,
        attendancePercentToday: 87.5,
        pendingHomeworkCount: 3,
      },
    })

    renderWithProviders(<DashboardPage />, { route: '/app/dashboard' })

    expect(screen.getByText(/Айгуль/)).toBeInTheDocument()
    expect(screen.getByText('87.5%')).toBeInTheDocument()
    expect(screen.getAllByText('Роботы-1').length).toBeGreaterThan(0)
    expect(screen.getByText(/домашних заданий ожидают проверки/)).toHaveTextContent('3')
  })

  it('shows a friendly empty state when there are no lessons today', () => {
    mockUseDashboardData.mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: {
        today: '2026-09-10',
        lessonsToday: [],
        nextLesson: null,
        studentsToday: 0,
        attendancePercentToday: null,
        pendingHomeworkCount: 0,
      },
    })

    renderWithProviders(<DashboardPage />, { route: '/app/dashboard' })

    expect(screen.getByText('На сегодня занятий нет')).toBeInTheDocument()
  })

  it('shows an error state with a retry action when the dashboard data fails to load', () => {
    const refetch = vi.fn()
    mockUseDashboardData.mockReturnValue({ isPending: false, isError: true, refetch, data: undefined })

    renderWithProviders(<DashboardPage />, { route: '/app/dashboard' })

    expect(screen.getByRole('button', { name: /повтор/i })).toBeInTheDocument()
  })
})
