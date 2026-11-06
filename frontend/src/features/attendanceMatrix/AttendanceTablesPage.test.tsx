import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { MatrixMeta, Overview } from '@/types/attendanceMatrix'

vi.mock('@/api/attendanceMatrix', () => ({
  attendanceMatrixApi: {
    group: vi.fn(), cell: vi.fn(), updateCell: vi.fn(), exportGroup: vi.fn(),
    meta: vi.fn(), overview: vi.fn(), exportOverview: vi.fn(), settings: vi.fn(), updateSettings: vi.fn(),
  },
}))

import { attendanceMatrixApi } from '@/api/attendanceMatrix'

import { AttendanceTablesPage } from './AttendanceTablesPage'

const api = vi.mocked(attendanceMatrixApi)

const META: MatrixMeta = {
  role: 'operations_director',
  groups: [
    { id: 1, name: 'Prog SOFT 1', status: 'active', course: 'Программатика', subject_ids: [3], teacher_ids: [7] },
    { id: 2, name: 'English 1', status: 'active', course: 'English', subject_ids: [4], teacher_ids: [8] },
  ],
  subjects: [{ id: 3, name: 'IT' }, { id: 4, name: 'English' }],
  teachers: [{ id: 7, name: 'Islam' }, { id: 8, name: 'Aizada' }],
}
const summary = {
  present: 0, late: 0, excused: 0, absent: 0, unmarked: 0, marked: 0, hw_done: 0, hw_missed: 0, hw_due: 0, done_cells: 0, lessons: 0,
  students: 0, percent: null, hw_percent: null, groups: 1,
  cards: { done: { count: 0, percent: null }, excused: { count: 0, percent: null }, absent: { count: 0, percent: null }, hw_missed: { count: 0, percent: null } },
  warnings: { critical: 0, attention: 0, warning: 0 },
}
const OVERVIEW = {
  period: { kind: 'month', start: '2026-11-01', end: '2026-11-30', label: 'Ноябрь 2026', prev: '2026-10-01', next: '2026-12-01' },
  summary, trainers: [], problem_students: [], ranking: [], trend: [], excused: [], assistants: [], history: [],
  thresholds: { consecutive_absences_warning: 2, monthly_absences_attention: 3, monthly_absences_critical: 4, missed_homework_warning: 3 },
  groups: [{ id: 1, name: 'Prog SOFT 1', course: 'Программатика', status: 'active', status_display: 'Активна', trainers: ['Islam'], students: 12, lessons: 8,
    percent: 91, hw_percent: 70, present: 80, excused: 2, absent: 6, unmarked: 0, hw_missed: 5, warnings: { critical: 0, attention: 0, warning: 0 } }],
} as Overview

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue(META)
  api.overview.mockResolvedValue(OVERVIEW)
  api.group.mockReturnValue(new Promise(() => {}))
})

describe('AttendanceTablesPage — the same tables for Assistant, Team Lead and Operations director', () => {
  it('lists the scoped groups with month stats; subject and trainer filters narrow them', async () => {
    renderWithProviders(<AttendanceTablesPage />, { route: '/operations/attendance?month=2026-11' })
    const table = await screen.findByRole('table')
    await within(table).findByText('91%')
    expect(within(table).getByText('English 1').closest('tr')).toHaveTextContent('нет занятий')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Предмет' }), '4')
    expect(within(screen.getByRole('table')).queryByText('Prog SOFT 1')).not.toBeInTheDocument()
    await waitFor(() => expect(api.overview).toHaveBeenLastCalledWith(expect.objectContaining({ subject: 4, date: '2026-11-01' })))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Предмет' }), '')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Тренер' }), '7')
    expect(within(screen.getByRole('table')).queryByText('English 1')).not.toBeInTheDocument()
  })

  it('opens the full table of a group for the chosen month, subject and trainer', async () => {
    renderWithProviders(<AttendanceTablesPage />, { route: '/operations/attendance?month=2026-10&subject=3&teacher=7' })
    await userEvent.click(await screen.findByRole('button', { name: 'Prog SOFT 1' }))
    await waitFor(() => expect(api.group).toHaveBeenCalledWith(1, expect.objectContaining({ date: '2026-10-01', subject: 3, teacher: 7, period: 'month' })))
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))
    await waitFor(() => expect(api.group).toHaveBeenLastCalledWith(1, expect.objectContaining({ date: '2026-09-01' })))
  })

  it('a group link from another page opens its table directly', async () => {
    renderWithProviders(<AttendanceTablesPage />, { route: '/operations/attendance?group=2' })
    await waitFor(() => expect(api.group).toHaveBeenCalledWith(2, expect.anything()))
    expect(screen.getByRole('button', { name: 'Все группы' })).toBeInTheDocument()
  })
})
