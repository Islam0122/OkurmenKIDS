import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { Overview } from '@/types/attendanceMatrix'

vi.mock('@/api/attendanceMatrix', () => ({
  attendanceMatrixApi: {
    group: vi.fn(), cell: vi.fn(), updateCell: vi.fn(), exportGroup: vi.fn(),
    meta: vi.fn(), overview: vi.fn(), exportOverview: vi.fn(), settings: vi.fn(), updateSettings: vi.fn(),
  },
}))

import { attendanceMatrixApi } from '@/api/attendanceMatrix'

import { AttendanceOverviewPage } from './AttendanceOverviewPage'

const api = vi.mocked(attendanceMatrixApi)
const summary = {
  present: 8, late: 0, excused: 2, absent: 2, unmarked: 0, marked: 12, hw_done: 4, hw_missed: 2, hw_due: 6, done_cells: 6, lessons: 12,
  students: 3, percent: 67, hw_percent: 67, groups: 1,
  cards: { done: { count: 6, percent: 50 }, excused: { count: 2, percent: 17 }, absent: { count: 2, percent: 17 }, hw_missed: { count: 2, percent: 33 } },
  warnings: { critical: 0, attention: 0, warning: 0 },
}
const OVERVIEW: Overview = {
  period: { kind: 'month', start: '2026-10-01', end: '2026-10-31', label: 'Октябрь 2026', prev: '2026-09-01', next: '2026-11-01' },
  summary, groups: [], trainers: [], problem_students: [], ranking: [], trend: [],
  thresholds: { consecutive_absences_warning: 2, monthly_absences_attention: 3, monthly_absences_critical: 4, missed_homework_warning: 3 },
  excused: [
    { id: 1, student: { id: 1, name: 'Бекнур' }, group: { id: 5, name: 'Prog SOFT 1' }, lesson_id: 10, date: '2026-10-05', reason: 'Справка от врача', comment: '', missing_reason: false, updated_by: { id: 1, name: 'Islam', role: 'teacher' } },
    { id: 2, student: { id: 2, name: 'Талант' }, group: { id: 5, name: 'Prog SOFT 1' }, lesson_id: 11, date: '2026-10-07', reason: '', comment: '', missing_reason: true, updated_by: null },
  ],
  assistants: [{ user: { id: 9, name: 'Asel', role: 'assistant' }, changes: 4, attendance_changes: 3, homework_changes: 1, comments: 2, students: 3, groups: ['Prog SOFT 1'], last_change: '2026-10-07T10:00:00Z' }],
  history: [{
    id: 1, at: '2026-10-07T10:00:00Z', actor: { id: 9, name: 'Asel', role: 'assistant' }, actor_role: 'assistant',
    student: { id: 2, name: 'Талант' }, group: { id: 5, name: 'Prog SOFT 1' }, lesson_id: 11, date: '2026-10-07',
    changes: [{ field: 'attendance', label: 'Посещаемость', before: '—', after: 'Отсутствовал' }],
  }],
}

beforeEach(() => {
  vi.clearAllMocks()
  api.meta.mockResolvedValue({ role: 'team_lead', groups: [{ id: 5, name: 'Prog SOFT 1', status: 'active', course: 'Программатика', subject_ids: [3], teacher_ids: [1] }], subjects: [], teachers: [] })
  api.overview.mockResolvedValue(OVERVIEW)
})

describe('AttendanceOverviewPage — what a Team Lead checks', () => {
  it('excused reasons, with the ones without a reason flagged and filterable', async () => {
    renderWithProviders(<AttendanceOverviewPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Уважительные причины (2)' }))
    expect(screen.getByText('Справка от врача')).toBeInTheDocument()
    expect(screen.getByText('Не указана')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('checkbox', { name: /Только без указанной причины/ }))
    expect(screen.queryByText('Справка от врача')).not.toBeInTheDocument()
  })

  it("assistants' work and the journal of changes", async () => {
    renderWithProviders(<AttendanceOverviewPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Ассистенты (1)' }))
    const row = screen.getByText('Asel').closest('tr') as HTMLElement
    expect(within(row).getAllByRole('cell').map((c) => c.textContent).slice(0, 7)).toEqual(['Asel', 'Prog SOFT 1', '4', '3', '1', '2', '3'])
    await userEvent.click(screen.getByRole('tab', { name: 'Журнал изменений' }))
    expect(screen.getByText('Посещаемость: — → Отсутствовал')).toBeInTheDocument()
  })
})
