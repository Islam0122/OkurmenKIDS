import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AcademyReportTeachersTable } from '@/features/academyReport/AcademyReportTeachersTable'
import type { AcademyReportTeacherRow } from '@/types/academyReport'

const row = (overrides: Partial<AcademyReportTeacherRow>): AcademyReportTeacherRow => ({
  id: 1,
  name: 'Азиза Садыкова',
  lessons_completed: 3,
  students_count: 3,
  attendance_rate: 88.9,
  homework_rate: 66.7,
  progress_rate: 80,
  activity_rate: 75,
  test_score_rate: 73.3,
  kpi_total: 76.8,
  ...overrides,
})

describe('AcademyReportTeachersTable', () => {
  it('shows the five KPI criteria per teacher, «Нет данных» without tests', () => {
    render(
      <AcademyReportTeachersTable
        teachers={[row({}), row({ id: 2, name: 'Бек Токтогулов', test_score_rate: null, kpi_total: 95 })]}
      />,
    )
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Преподаватель', 'Занятия', 'Студенты', 'Посещаемость', 'ДЗ', 'Прогресс', 'Активность', 'Результаты тестов', 'KPI',
    ])
    const first = within(table).getByText('Азиза Садыкова').closest('tr') as HTMLElement
    for (const value of ['88,9%', '66,7%', '80%', '75%', '73,3%', '76,8%']) {
      expect(within(first).getByText(value)).toBeInTheDocument()
    }
    const second = within(table).getByText('Бек Токтогулов').closest('tr') as HTMLElement
    expect(within(second).getByText('Нет данных')).toBeInTheDocument()
  })
})
