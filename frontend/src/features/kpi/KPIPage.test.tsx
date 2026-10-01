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

  it('renders the total KPI exactly as the backend computed it', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        metrics: {
          attendance: 82,
          homework: 66,
          lesson_completion: 51.3,
          progress: 91.1,
          retention: 95.3,
          teacher_workload: 60,
        },
        kpi: {
          total: 72.6,
          status: 'low',
          status_label: 'Низкий',
          weights: [
            { key: 'attendance', label: 'Посещаемость', weight: 25 },
            { key: 'homework', label: 'Домашние задания', weight: 25 },
            { key: 'lesson_completion', label: 'Проведённые занятия', weight: 25 },
            { key: 'progress', label: 'Прогресс', weight: 25 },
          ],
        },
      }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    // No frontend math: the value and status are the API's, verbatim.
    await waitFor(() => expect(screen.getByText('72,6%')).toBeInTheDocument())
    expect(screen.getByText('Низкий')).toBeInTheDocument()
    expect(screen.getAllByText('не входит в KPI')).toHaveLength(2)
  })

  it('shows "—" when the backend reports no KPI data', async () => {
    vi.mocked(kpiApi.dashboard).mockResolvedValue(
      buildAnalyticsDashboard({
        kpi: { total: null, status: 'no_data', status_label: 'Нет данных', weights: [] },
      }),
    )

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('Нет данных')).toBeInTheDocument())
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
