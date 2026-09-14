import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LessonDetailPage } from '@/features/lessons/LessonDetailPage'
import { buildHomework, buildLesson, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/lessons', () => ({
  lessonsApi: {
    get: vi.fn(),
    getAttendanceRoster: vi.fn(),
    list: vi.fn(),
    saveAttendance: vi.fn(),
    start: vi.fn(),
    complete: vi.fn(),
    cancel: vi.fn(),
    setHomeworkNotRequired: vi.fn(),
  },
}))
vi.mock('@/api/homework', () => ({
  homeworkApi: { list: vi.fn(), get: vi.fn(), getResultsRoster: vi.fn(), saveResults: vi.fn(), create: vi.fn() },
}))

import { homeworkApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'

function renderLessonDetail(id = 7) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/lessons/:id" element={<LessonDetailPage />} />
      <Route path="/app/attendance" element={<div>Attendance page</div>} />
      <Route path="/app/homework/:id" element={<div>Homework detail page</div>} />
    </Routes>,
    { route: `/app/lessons/${id}` },
  )
}

describe('LessonDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the real lesson info and attendance breakdown, and links to the linked homework', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(
      buildLesson({ id: 7, subject_name: 'Робототехника', topic: 'Введение в конструктор', group_name: 'Роботы-1' }),
    )
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      { id: 1, student: 1, student_name: 'A', lesson: 7, group_name: 'Роботы-1', lesson_date: '2026-09-10', status: 'present', status_display: 'Присутствовал', comment: '', created_at: null, updated_at: null },
      { id: 2, student: 2, student_name: 'B', lesson: 7, group_name: 'Роботы-1', lesson_date: '2026-09-10', status: 'absent', status_display: 'Отсутствовал', comment: '', created_at: null, updated_at: null },
    ])
    vi.mocked(homeworkApi.list).mockResolvedValue(paginated([buildHomework({ id: 55, lesson: 7 })]))

    renderLessonDetail(7)

    await waitFor(() => expect(screen.getByText('Введение в конструктор', { exact: false })).toBeInTheDocument())
    expect(screen.getByText('Роботы-1')).toBeInTheDocument()

    await waitFor(() => expect(screen.getByRole('button', { name: 'Открыть ДЗ' })).toBeInTheDocument())
  })

  it('navigates to the attendance screen for this lesson when "Отметить посещаемость" is clicked', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7 }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
    vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

    const user = userEvent.setup()
    renderLessonDetail(7)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Отметить посещаемость' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Отметить посещаемость' }))

    expect(await screen.findByText('Attendance page')).toBeInTheDocument()
  })

  it('shows a "Start lesson" button for a scheduled lesson and starts it', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status: 'scheduled', can_start: true }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
    vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
    vi.mocked(lessonsApi.start).mockResolvedValue(
      buildLesson({ id: 7, status: 'in_progress', can_start: false, can_complete: false, can_cancel: true }),
    )

    const user = userEvent.setup()
    renderLessonDetail(7)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Начать занятие' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Начать занятие' }))

    await waitFor(() => expect(lessonsApi.start).toHaveBeenCalledWith(7))
  })

  it('blocks completion and shows the missing requirements while in progress', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(
      buildLesson({
        id: 7,
        status: 'in_progress',
        can_start: false,
        can_complete: false,
        can_cancel: true,
        completion_requirements: [
          { key: 'attendance', label: 'Посещаемость отмечена', satisfied: false },
          { key: 'homework', label: 'Добавлено домашнее задание или отмечено «ДЗ не требуется»', satisfied: false },
        ],
        completion_progress: { satisfied: 0, total: 2, is_complete: false },
      }),
    )
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
    vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

    renderLessonDetail(7)

    const completeButton = await screen.findByRole('button', { name: 'Завершить занятие' })
    expect(completeButton).toBeDisabled()
    expect(screen.getByText(/Нельзя завершить занятие/)).toBeInTheDocument()
  })

  it('completes an in-progress lesson once requirements are satisfied', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(
      buildLesson({
        id: 7,
        status: 'in_progress',
        can_start: false,
        can_complete: true,
        can_cancel: true,
        completion_requirements: [
          { key: 'attendance', label: 'Посещаемость отмечена', satisfied: true },
          { key: 'homework', label: 'Добавлено домашнее задание или отмечено «ДЗ не требуется»', satisfied: true },
        ],
        completion_progress: { satisfied: 2, total: 2, is_complete: true },
        homework_not_required: true,
      }),
    )
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
    vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
    vi.mocked(lessonsApi.complete).mockResolvedValue(buildLesson({ id: 7, status: 'completed' }))

    const user = userEvent.setup()
    renderLessonDetail(7)

    const completeButton = await screen.findByRole('button', { name: 'Завершить занятие' })
    expect(completeButton).not.toBeDisabled()
    await user.click(completeButton)

    await waitFor(() => expect(lessonsApi.complete).toHaveBeenCalledWith(7))
  })
})
