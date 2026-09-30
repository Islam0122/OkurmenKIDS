import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ControlPage } from '@/features/control/ControlPage'
import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { ControlLesson, ControlOverview, ControlRow } from '@/types/control'

const mockRole = vi.hoisted(() => ({ role: 'admin' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/control', () => ({ controlApi: { overview: vi.fn(), detail: vi.fn(), lesson: vi.fn() } }))

import { controlApi } from '@/api/control'

const component = (completed: number, total: number, level: 'ok' | 'warning' | 'danger' | 'none') => ({
  completed,
  total,
  percent: total ? Math.round((completed / total) * 1000) / 10 : null,
  level,
})

function buildRow(overrides: Partial<ControlRow> = {}): ControlRow {
  return {
    key: '1-2',
    teacher: { id: 1, name: 'Айжан', is_active: true },
    group: { id: 2, name: 'Prog Soft 2' },
    subjects: [{ id: 1, name: 'Python' }],
    lessons: { ...component(8, 8, 'ok'), not_closed: 0, upcoming: 1, cancelled: 0 },
    attendance: component(8, 8, 'ok'),
    homework: component(5, 7, 'warning'),
    grades: { ...component(4, 8, 'danger'), students_missing: 3 },
    status: 'attention',
    status_label: 'Требует внимания',
    problem_lessons: 4,
    issues: ['Без балла: 3 оценки на 4 занятия'],
    first_problem_lesson_id: 28,
    last_activity_at: '2026-09-30T13:42:00+06:00',
    ...overrides,
  }
}

function buildOverview(items: ControlRow[]): ControlOverview {
  return {
    filters: {
      period: 'this_month',
      period_label: 'Сентябрь 2026',
      start_date: '2026-09-01',
      end_date: '2026-09-30',
      program: null,
      group: null,
      teacher: null,
      subject: null,
      status: null,
    },
    summary: {
      total_lessons: 48,
      completed_lessons: 42,
      not_closed_lessons: 6,
      upcoming_lessons: 3,
      cancelled_lessons: 1,
      attendance_completion: 92,
      homework_completion: 76,
      grade_completion: 87.5,
      students_without_grade: 3,
      attention_count: 8,
      problem_lessons: 10,
      rows_total: items.length,
      status_counts: { ok: 1, attention: 1, not_filled: 0, no_data: 0, upcoming: 0 },
    },
    items,
    options: {
      periods: [
        { key: 'this_month', label: 'Сентябрь 2026' },
        { key: 'custom', label: 'Произвольный период' },
      ],
      teachers: [{ id: 1, name: 'Айжан' }],
      groups: [{ id: 2, name: 'Prog Soft 2' }],
      subjects: [{ id: 1, name: 'Python' }],
      statuses: [
        { key: 'not_filled', label: 'Не заполнено' },
        { key: 'attention', label: 'Требует внимания' },
        { key: 'ok', label: 'OK' },
      ],
    },
  }
}

function buildLesson(overrides: Partial<ControlLesson> = {}): ControlLesson {
  return {
    id: 28,
    lesson_number: 28,
    date: '2026-09-30',
    start_time: '10:00:00',
    end_time: '11:30:00',
    topic: 'Циклы',
    subject: { id: 1, name: 'Python' },
    group: { id: 2, name: 'Prog Soft 2' },
    teacher: { id: 1, name: 'Айжан', is_active: true },
    planned_teacher: null,
    state: 'due',
    lesson_status: 'completed',
    lesson_status_label: 'Проведён',
    closed: true,
    closed_at: '2026-09-30T13:42:00+06:00',
    closed_by: { id: 5, name: 'Айжан' },
    status: 'attention',
    status_label: 'Требует внимания',
    students_total: 20,
    attendance: { state: 'ok', marked: 20, total: 20, missing_students: [] },
    homework: { state: 'ok', id: 3, given: true, not_required: false, deadline: null, pending_check: 0 },
    grades: {
      state: 'partial',
      given: 17,
      total: 20,
      missing: 3,
      missing_students: [
        { id: 1, name: 'Камалидинова Сумая' },
        { id: 2, name: 'Азамат уулу Али' },
        { id: 3, name: 'Иванов Артём' },
      ],
    },
    problems: ['Без балла: 3 студента'],
    notes: [],
    last_activity_at: '2026-09-30T13:42:00+06:00',
    ...overrides,
  }
}

describe('ControlPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'admin'
  })

  it('shows the backend summary and rows verbatim', async () => {
    vi.mocked(controlApi.overview).mockResolvedValue(buildOverview([buildRow()]))

    renderWithProviders(<ControlPage />, { route: '/app/control' })

    await waitFor(() => expect(screen.getAllByText('Требует внимания').length).toBeGreaterThan(0))
    expect(screen.getByText('48')).toBeInTheDocument()
    expect(screen.getByText('87,5%')).toBeInTheDocument()
    expect(screen.getAllByText('5/7').length).toBeGreaterThan(0)
    expect(screen.getAllByText('4/8').length).toBeGreaterThan(0)
    expect(controlApi.overview).toHaveBeenCalledWith({ period: 'this_month' })
  })

  it('applies filters only on «Применить» and resets them', async () => {
    const user = userEvent.setup()
    vi.mocked(controlApi.overview).mockResolvedValue(buildOverview([buildRow()]))

    renderWithProviders(<ControlPage />, { route: '/app/control' })
    await waitFor(() => expect(screen.getByRole('option', { name: 'Prog Soft 2' })).toBeInTheDocument())

    await user.selectOptions(screen.getByLabelText('Группа'), '2')
    await user.selectOptions(screen.getByLabelText('Статус'), 'attention')
    expect(controlApi.overview).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Применить' }))
    await waitFor(() =>
      expect(controlApi.overview).toHaveBeenLastCalledWith({ period: 'this_month', group: 2, status: 'attention' }),
    )

    await user.click(screen.getByRole('button', { name: 'Сбросить' }))
    await waitFor(() => expect(controlApi.overview).toHaveBeenLastCalledWith({ period: 'this_month' }))
  })

  it('opens a row with its lessons, students without a score and a link to the lesson', async () => {
    const user = userEvent.setup()
    vi.mocked(controlApi.overview).mockResolvedValue(buildOverview([buildRow()]))
    vi.mocked(controlApi.detail).mockResolvedValue({
      filters: buildOverview([]).filters,
      row: buildRow(),
      lessons: [buildLesson(), buildLesson({ id: 40, date: '2026-10-02', state: 'upcoming', status: 'upcoming', status_label: 'Предстоящий', problems: [] })],
    })

    renderWithProviders(<ControlPage />, { route: '/app/control' })
    const cell = await screen.findByRole('cell', { name: 'Айжан' })

    await user.click(cell)
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(within(dialog).getByText('30.09.2026')).toBeInTheDocument())
    expect(controlApi.detail).toHaveBeenCalledWith(expect.objectContaining({ group: 2, teacher: 1, period: 'this_month' }))
    expect(within(dialog).getByText('Предстоящий')).toBeInTheDocument()

    await user.click(within(dialog).getByText('30.09.2026'))
    expect(within(dialog).getByText(/Выставлено: 17 \/ 20/)).toBeInTheDocument()
    expect(within(dialog).getByText('• Камалидинова Сумая')).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: /Перейти к уроку/ })).toHaveAttribute('href', '/app/lessons/28')
  })

  it('hides the trainer filter from a trainer', async () => {
    mockRole.role = 'teacher'
    vi.mocked(controlApi.overview).mockResolvedValue(buildOverview([]))

    renderWithProviders(<ControlPage />, { route: '/app/control' })

    await waitFor(() => expect(screen.getByText('Нет занятий')).toBeInTheDocument())
    expect(screen.queryByLabelText('Тренер')).not.toBeInTheDocument()
  })
})
