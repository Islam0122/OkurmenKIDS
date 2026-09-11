import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KPIPage } from '@/features/kpi/KPIPage'
import { buildAnalyticsDashboard, buildMetric, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/kpi', () => ({ kpiApi: { dashboard: vi.fn() } }))
vi.mock('@/api/groups', () => ({ groupsApi: { list: vi.fn(), get: vi.fn(), schedule: vi.fn(), students: vi.fn() } }))
vi.mock('@/api/subjects', () => ({ subjectsApi: { list: vi.fn() } }))

import { groupsApi } from '@/api/groups'
import { kpiApi } from '@/api/kpi'
import { subjectsApi } from '@/api/subjects'

describe('KPIPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(groupsApi.list).mockResolvedValue(paginated([]))
    vi.mocked(subjectsApi.list).mockResolvedValue(paginated([]))
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-10T10:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the real numbers computed for the selected period — nothing invented', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        attendance: {
          attendance_rate: buildMetric(92.5),
          present_count: buildMetric(30),
          absent_count: buildMetric(5),
          late_count: buildMetric(5),
          excused_count: buildMetric(0),
          students_with_repeated_absences: buildMetric(0),
          attendance_trend: [],
        },
        homework: {
          homework_count: buildMetric(10),
          submitted_count: buildMetric(10),
          not_submitted_count: buildMetric(3),
          checked_count: buildMetric(3),
          late_count: buildMetric(0),
          submission_rate: buildMetric(80),
          average_score: buildMetric(8.4),
          homework_completion_trend: [],
        },
      }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('92.5%')).toBeInTheDocument())
    expect(screen.getAllByText('80%').length).toBeGreaterThan(0)
    expect(screen.getByText('8.4/10')).toBeInTheDocument()
  })

  it('renders the Academy Health score', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({ health: { score: 73, level: 'fair', components: { attendance: 70, homework: 75, lesson_completion: 80, retention: 65, teacher_workload: 75 } } }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('73')).toBeInTheDocument())
    expect(screen.getByText('Средне')).toBeInTheDocument()
  })

  it('shows an explicit empty message instead of a fabricated insight', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(buildAnalyticsDashboard({ insights: [] }))

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() =>
      expect(screen.getByText('Ничего не требует внимания за выбранный период.')).toBeInTheDocument(),
    )
  })

  it('surfaces a real insight with its severity', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        insights: [
          {
            type: 'warning',
            title: 'Посещаемость снизилась',
            message: 'Посещаемость упала на 12% по сравнению с прошлым периодом.',
            metric: 'attendance_rate',
            severity: 'high',
          },
        ],
      }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('Посещаемость снизилась')).toBeInTheDocument())
    expect(screen.getByText(/упала на 12%/)).toBeInTheDocument()
  })

  it('requests the selected period and no comparison by default', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(buildAnalyticsDashboard())

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() =>
      expect(kpiApi.dashboard).toHaveBeenCalledWith(
        expect.objectContaining({ period: 'this_month', start_date: '2026-09-01', end_date: '2026-09-10' }),
      ),
    )
    expect(kpiApi.dashboard).not.toHaveBeenCalledWith(expect.objectContaining({ compare: expect.anything() }))
  })
})
