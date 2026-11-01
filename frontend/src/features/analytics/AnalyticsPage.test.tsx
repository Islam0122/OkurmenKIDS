import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AnalyticsPage } from '@/features/analytics/AnalyticsPage'
import { renderWithProviders } from '@/test/testUtils'
import type { ReportOverview, ReportPage, ReportParams, ReportTeacherRow } from '@/types/reports'

vi.mock('@/api/reports', () => ({
  reportsApi: { overview: vi.fn(), teachers: vi.fn(), groups: vi.fn(), students: vi.fn(), subjects: vi.fn() },
}))

import { reportsApi } from '@/api/reports'

/** Students per month as the backend reports them for that month alone. */
const STUDENTS_BY_START: Record<string, number> = { '2026-09-01': 97, '2026-10-01': 110 }

function overviewFor(params: ReportParams): ReportOverview {
  const students = STUDENTS_BY_START[params.start_date ?? ''] ?? 0
  return {
    filters: { period: params.period, period_label: 'Период', start_date: params.start_date ?? '', end_date: params.end_date ?? '' },
    students: { total: students, active: students, left: 0, new: 0, retention_rate: null },
    teachers: { total: 5, with_groups: 5, without_groups: 0 },
    groups: { total: 8, active: 8, without_teacher: 0 },
    kpi: { total: 80 },
    attendance: { rate: 90 },
    homework: { completion_rate: 70, average_score: 8 },
    lessons: { held: 10, total: 12 },
    has_data: true,
    top_groups: [],
    attention_groups: [],
  } as unknown as ReportOverview
}

const EMPTY_PAGE: ReportPage<ReportTeacherRow> = { count: 0, page: 1, pages: 1, page_size: 25, search: '', sort: '-kpi', results: [] }

const SEPTEMBER = { period: 'custom', start_date: '2026-09-01', end_date: '2026-09-30' }
const OCTOBER = { period: 'custom', start_date: '2026-10-01', end_date: '2026-10-31' }

function chooseMonth(value: string) {
  fireEvent.change(screen.getByRole('combobox', { name: 'Период' }), { target: { value } })
}

describe('AnalyticsPage → month switch (Team Lead)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 1, 10))
    vi.mocked(reportsApi.overview).mockImplementation(async (params: ReportParams) => overviewFor(params))
    vi.mocked(reportsApi.teachers).mockResolvedValue(EMPTY_PAGE)
    vi.mocked(reportsApi.groups).mockResolvedValue(EMPTY_PAGE as never)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('September → 97, October → 110, back to September → 97', async () => {
    renderWithProviders(<AnalyticsPage />, { route: '/app/analytics' })

    chooseMonth('2026-09')
    expect(await screen.findByText('97 (97)')).toBeInTheDocument()
    expect(reportsApi.overview).toHaveBeenLastCalledWith(SEPTEMBER)
    // The tables are asked for the same month, not «this month».
    await waitFor(() => expect(reportsApi.teachers).toHaveBeenLastCalledWith(expect.objectContaining(SEPTEMBER)))

    chooseMonth('2026-10')
    expect(await screen.findByText('110 (110)')).toBeInTheDocument()
    expect(screen.queryByText('97 (97)')).not.toBeInTheDocument()
    expect(reportsApi.overview).toHaveBeenLastCalledWith(OCTOBER)

    chooseMonth('2026-09')
    expect(await screen.findByText('97 (97)')).toBeInTheDocument()
    expect(screen.queryByText('110 (110)')).not.toBeInTheDocument()
  })

  it('opening the page with September in the URL (a refresh) shows September', async () => {
    renderWithProviders(<AnalyticsPage />, { route: '/app/analytics?tab=groups&period=2026-09' })
    expect(await screen.findByText('97 (97)')).toBeInTheDocument()
    expect(reportsApi.overview).toHaveBeenCalledTimes(1)
    expect(reportsApi.overview).toHaveBeenCalledWith(SEPTEMBER)
    expect(screen.getByRole('combobox', { name: 'Период' })).toHaveValue('2026-09')
  })

  it('never keeps the previous month on screen while the new one loads', async () => {
    renderWithProviders(<AnalyticsPage />, { route: '/app/analytics?period=2026-10' })
    expect(await screen.findByText('110 (110)')).toBeInTheDocument()

    let resolveSeptember: (value: ReportOverview) => void = () => {}
    vi.mocked(reportsApi.overview).mockImplementationOnce(
      () => new Promise<ReportOverview>((resolve) => { resolveSeptember = resolve }),
    )
    chooseMonth('2026-09')
    await waitFor(() => expect(screen.queryByText('110 (110)')).not.toBeInTheDocument())
    expect(screen.getByText('Считаем показатели за период…')).toBeInTheDocument()

    resolveSeptember(overviewFor(SEPTEMBER as ReportParams))
    expect(await screen.findByText('97 (97)')).toBeInTheDocument()
  })
})
