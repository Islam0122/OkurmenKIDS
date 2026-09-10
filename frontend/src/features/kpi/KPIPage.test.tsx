import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KPIPage } from '@/features/kpi/KPIPage'
import { buildKPITeacher, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/kpi', () => ({
  kpiApi: { groups: vi.fn(), teachers: vi.fn(), students: vi.fn(), lessons: vi.fn(), attendance: vi.fn(), homework: vi.fn() },
}))

import { kpiApi } from '@/api/kpi'

describe('KPIPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-10T10:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the real numbers from the most recent KPITeacher snapshot — nothing invented', async () => {
    const snapshot = buildKPITeacher({
      attendance_percent: 92.5,
      homework_completion_percent: 80,
      average_student_score: 8.4,
      total_lessons: 10,
      total_groups: 2,
    })
    vi.mocked(kpiApi.teachers).mockResolvedValue(paginated([snapshot]))

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('92.5%')).toBeInTheDocument())
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('8.4/10')).toBeInTheDocument()
  })

  it('shows an explicit empty state instead of a fabricated chart when no snapshot exists yet', async () => {
    vi.mocked(kpiApi.teachers).mockResolvedValue(paginated([]))

    renderWithProviders(<KPIPage />, { route: '/app/kpi' })

    await waitFor(() => expect(screen.getByText('KPI-снимков пока нет')).toBeInTheDocument())
  })
})
