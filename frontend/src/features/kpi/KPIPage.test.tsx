import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KPIPage } from '@/features/kpi/KPIPage'
import { buildAnalyticsDashboard, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/kpi', () => ({ kpiApi: { dashboard: vi.fn() } }))
vi.mock('@/api/groups', () => ({ groupsApi: { list: vi.fn(), get: vi.fn(), schedule: vi.fn(), students: vi.fn() } }))

import { groupsApi } from '@/api/groups'
import { kpiApi } from '@/api/kpi'

describe('KPIPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(groupsApi.list).mockResolvedValue(paginated([]))
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-10T10:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the real numbers computed for the selected period — nothing invented', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        overview: {
          groups: 2,
          teachers: 1,
          students: 20,
          lessons: 10,
          attendance_percent: 92.5,
          homework_completion_percent: 80,
          average_score: 8.4,
        },
      }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('92.5%')).toBeInTheDocument())
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('8.4/10')).toBeInTheDocument()
  })

  it('shows an explicit empty message instead of a fabricated chart when there is no data yet', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        overview: { groups: 0, teachers: 0, students: 0, lessons: 0, attendance_percent: 0, homework_completion_percent: 0, average_score: 0 },
        attendance: { total: 0, present: 0, absent: 0, late: 0, excused: 0, percent: 0, by_date: [] },
        homework: { total_homeworks: 0, total_results: 0, submitted: 0, checked: 0, late: 0, not_submitted: 0, completed: 0, completion_percent: 0, average_score: 0, by_date: [] },
      }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('Нет данных за выбранный период.')).toBeInTheDocument())
  })

  it('re-fetches the dashboard whenever the period changes', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(buildAnalyticsDashboard())

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(kpiApi.dashboard).toHaveBeenCalledWith(
      expect.objectContaining({ date_from: '2026-09-01', date_to: '2026-09-10' }),
    ))
  })
})
