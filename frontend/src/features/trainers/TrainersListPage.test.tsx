import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TrainersListPage } from '@/features/trainers/TrainersListPage'
import { renderWithProviders } from '@/test/testUtils'
import type { ReportPage, ReportTeacherRow } from '@/types/reports'

vi.mock('@/api/reports', () => ({ reportsApi: { teachers: vi.fn() } }))

import { reportsApi } from '@/api/reports'

function teacherRow(overrides: Partial<ReportTeacherRow>): ReportTeacherRow {
  return {
    id: 1,
    name: 'Айбек Асанов',
    position: 'Тренер',
    is_active: true,
    groups: [],
    groups_count: 0,
    subjects: ['Python'],
    students: { total: 0, active: 0, left: 0 },
    lessons: { total: 0, held: 0 },
    attendance_rate: 83.1,
    homework_rate: 80.9,
    progress_rate: 77.7,
    activity_rate: 95.5,
    test_score_rate: 72.1,
    test_pass_rate: 60,
    kpi: 81.9,
    kpi_level: 'attention',
    has_data: true,
    ...overrides,
  }
}

function page(results: ReportTeacherRow[]): ReportPage<ReportTeacherRow> {
  return { count: results.length, page: 1, pages: 1, page_size: 25, search: '', sort: '-kpi', results }
}

describe('TrainersListPage → KPI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the five KPI criteria and the backend total, «Нет данных» when no tests were held', async () => {
    vi.mocked(reportsApi.teachers).mockResolvedValue(
      page([
        teacherRow({}),
        teacherRow({ id: 2, name: 'Бакыт Тренеров', test_score_rate: null, test_pass_rate: null, kpi: 84.3 }),
      ]),
    )

    renderWithProviders(<TrainersListPage />, { route: '/app/trainers' })
    fireEvent.click(await screen.findByRole('tab', { name: 'KPI' }))

    await waitFor(() => expect(screen.getByText('Результаты тестов')).toBeInTheDocument())
    const headers = screen.getAllByRole('columnheader').map((cell) => cell.textContent)
    expect(headers).toEqual([
      'Тренер',
      'Посещаемость',
      'ДЗ',
      'Прогресс',
      'Активность',
      'Результаты тестов',
      'Общий KPI',
    ])

    const first = screen.getByText('Айбек Асанов').closest('tr') as HTMLElement
    for (const value of ['83,1%', '80,9%', '77,7%', '95,5%', '72,1%', '81,9%']) {
      expect(within(first).getByText(value)).toBeInTheDocument()
    }
    const second = screen.getByText('Бакыт Тренеров').closest('tr') as HTMLElement
    expect(within(second).getByText('Нет данных')).toBeInTheDocument()
    expect(within(second).getByText('84,3%')).toBeInTheDocument()
    expect(vi.mocked(reportsApi.teachers)).toHaveBeenLastCalledWith(expect.objectContaining({ sort: '-kpi' }))
  })
})
