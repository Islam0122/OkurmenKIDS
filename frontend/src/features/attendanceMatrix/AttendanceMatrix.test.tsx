import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { CellDetail, GroupMatrix, MatrixRow } from '@/types/attendanceMatrix'

vi.mock('@/api/attendanceMatrix', () => ({
  attendanceMatrixApi: {
    group: vi.fn(), cell: vi.fn(), updateCell: vi.fn(), exportGroup: vi.fn(),
    meta: vi.fn(), overview: vi.fn(), exportOverview: vi.fn(), settings: vi.fn(), updateSettings: vi.fn(),
  },
}))

import { attendanceMatrixApi } from '@/api/attendanceMatrix'

import { AttendanceMatrix } from './AttendanceMatrix'

const api = vi.mocked(attendanceMatrixApi)

const stats = (present: number, excused: number, absent: number, percent: number | null) => ({
  present, late: 0, excused, absent, unmarked: 0, marked: present + excused + absent, lessons: 3, percent,
  hw_done: present, hw_missed: 0, hw_due: present, hw_percent: 100, done_cells: present, consecutive_absences: absent,
})

const row = (id: number, name: string, codes: MatrixRow['cells'][number]['code'][], s: MatrixRow['stats'], level: MatrixRow['level'] = null): MatrixRow => ({
  student: { id, name, status: 'active', status_display: 'Активен', in_group: true },
  cells: codes.map((code, i) => ({ lesson_id: 100 + i, code, attendance: null, homework: 'none', has_comment: false })),
  stats: s,
  warnings: level ? [{ code: 'absences_in_row', level, label: '2 пропуска подряд' }] : [],
  level,
})

const col = (i: number, date: string, weekday: string) => ({
  lesson_id: 100 + i, date, weekday, start: '16:00', end: '17:30', lesson_number: i + 1, topic: `Тема ${i + 1}`, subject: 'Python',
  teacher: 'Islam', teacher_id: 1, status: 'completed', held: true, editable_day: true, has_homework: false, can_edit: true,
  stats: { present: 1, excused: 0, absent: 1, unmarked: 0, hw_missed: 0, marked: 2, percent: 50 },
})

const MATRIX: GroupMatrix = {
  group: { id: 5, name: 'Prog SOFT 1', status: 'active', status_display: 'Активна', course: 'Программатика', students_count: 2 },
  period: { kind: 'month', start: '2026-06-01', end: '2026-06-30', label: 'Июнь 2026', prev: '2026-05-01', next: '2026-07-01' },
  columns: [col(0, '2026-06-12', 'Пт'), col(1, '2026-06-13', 'Сб'), col(2, '2026-06-15', 'Пн')],
  rows: [
    row(1, 'Бекнур Абдыбеков', ['done', 'excused', 'done'], stats(2, 1, 0, 67)),
    row(2, 'Талант Аманжолов', ['absent', 'absent', 'partial'], stats(1, 0, 2, 33), 'warning'),
  ],
  summary: {
    present: 3, late: 0, excused: 1, absent: 2, unmarked: 0, marked: 6, hw_done: 3, hw_missed: 0, hw_due: 3, done_cells: 2, lessons: 6,
    students: 2, percent: 50, hw_percent: 100,
    cards: { done: { count: 2, percent: 33 }, excused: { count: 1, percent: 17 }, absent: { count: 2, percent: 33 }, hw_missed: { count: 0, percent: 0 } },
    warnings: { critical: 0, attention: 0, warning: 1 },
  },
  ranking: [{ place: 1, student: { id: 1, name: 'Бекнур Абдыбеков', status: 'active', status_display: 'Активен', in_group: true }, percent: 67, present: 2, absent: 0, hw_percent: 100 }],
  thresholds: { consecutive_absences_warning: 2, monthly_absences_attention: 3, monthly_absences_critical: 4, missed_homework_warning: 3 },
  capabilities: { role: 'teacher', can_edit: true, can_comment: true, can_view_history: true, can_export: true },
  legend: [],
  filtered: false,
}

const CELL: CellDetail = {
  student: { id: 2, name: 'Талант Аманжолов' },
  group: { id: 5, name: 'Prog SOFT 1' },
  lesson: { id: 100, date: '2026-06-12', start: '16:00', end: '17:30', topic: 'Тема 1', number: 1, subject: 'Python', teacher: 'Islam', status: 'completed', status_display: 'Проведён', held: true },
  attendance: 'absent', excuse_reason: '', comment: '', homework: 'none', homeworks: [], homework_not_required: false,
  updated_by: { id: 1, name: 'Islam', role: 'teacher' }, updated_at: '2026-06-12T12:00:00Z', edit_level: 'full', edit_reason: '',
  history: [{ id: 1, at: '2026-06-12T12:00:00Z', actor: { id: 1, name: 'Islam', role: 'teacher' }, actor_role: 'teacher', changes: [{ field: 'attendance', label: 'Посещаемость', before: '—', after: 'Отсутствовал' }] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  api.group.mockResolvedValue(MATRIX)
  api.cell.mockResolvedValue(CELL)
  api.updateCell.mockResolvedValue({ ...CELL, attendance: 'excused', excuse_reason: 'Болел' })
})

describe('AttendanceMatrix', () => {
  it('shows students × lessons with statuses, totals and the group summary', async () => {
    renderWithProviders(<AttendanceMatrix groupId={5} />)
    expect(await screen.findByText('Июнь 2026')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(
      ['№', 'Студент', 'Пт12.06', 'Сб13.06', 'Пн15.06', 'Прис.', 'Уваж.', 'Отс.', 'ДЗ ✕', '%'],
    )
    expect(screen.getByRole('button', { name: 'Бекнур Абдыбеков, 12.06: Присутствовал + сдал ДЗ' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Талант Аманжолов, 15.06: Присутствовал (без ДЗ)' })).toBeInTheDocument()
    expect(screen.getByText('Итого по группе').closest('tr')).toHaveTextContent('50%')
    expect(screen.getByText('Посетил + сдал ДЗ').parentElement).toHaveTextContent('33%')
    expect(screen.getAllByText('Предупреждение').length).toBeGreaterThan(0)
    expect(api.group).toHaveBeenCalledWith(5, expect.objectContaining({ period: 'month' }))
  })

  it('switches the period and filters by status on the server', async () => {
    renderWithProviders(<AttendanceMatrix groupId={5} />)
    await screen.findByText('Июнь 2026')
    await userEvent.click(screen.getByRole('radio', { name: 'Неделя' }))
    await waitFor(() => expect(api.group).toHaveBeenLastCalledWith(5, expect.objectContaining({ period: 'week' })))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Статус посещаемости' }), 'absent')
    await waitFor(() => expect(api.group).toHaveBeenLastCalledWith(5, expect.objectContaining({ status: 'absent' })))
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущий период' }))
    await waitFor(() => expect(api.group).toHaveBeenLastCalledWith(5, expect.objectContaining({ date: '2026-05-01' })))
  })

  it('opens a cell, requires a reason for «excused» and saves it', async () => {
    renderWithProviders(<AttendanceMatrix groupId={5} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Талант Аманжолов, 12.06: Не пришёл без причины' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Prog SOFT 1')).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('radio', { name: 'Уваж. причина' }))
    const save = within(dialog).getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled()
    await userEvent.type(within(dialog).getByPlaceholderText(/болел/i), 'Болел')
    await userEvent.click(within(dialog).getByRole('button', { name: /История/ }))
    expect(within(dialog).getByText(/— → Отсутствовал/)).toBeInTheDocument()
    await userEvent.click(save)
    await waitFor(() => expect(api.updateCell).toHaveBeenCalledWith(expect.objectContaining({
      lesson: 100, student: 2, attendance: 'excused', excuse_reason: 'Болел',
    })))
  })

  it('a read-only cell offers no saving', async () => {
    api.cell.mockResolvedValue({ ...CELL, edit_level: 'none', edit_reason: 'Доступен только просмотр.' })
    renderWithProviders(<AttendanceMatrix groupId={5} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Талант Аманжолов, 12.06: Не пришёл без причины' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Доступен только просмотр.')).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument()
    expect(within(dialog).getByRole('radio', { name: 'Присутствовал' })).toBeDisabled()
  })
})
