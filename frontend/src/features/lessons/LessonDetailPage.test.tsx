import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
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

  it('renders the real lesson info', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(
      buildLesson({ id: 7, subject_name: 'Робототехника', topic: 'Введение в конструктор', group_name: 'Роботы-1' }),
    )
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
    vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

    renderLessonDetail(7)

    await waitFor(() => expect(screen.getByText('Введение в конструктор', { exact: false })).toBeInTheDocument())
    expect(screen.getByText('Роботы-1')).toBeInTheDocument()
  })

  describe('scheduled lesson', () => {
    it('shows only "Начать занятие" — no attendance/homework actions before the lesson starts', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status: 'scheduled', can_start: true, can_cancel: true }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([buildHomework({ id: 55, lesson: 7 })]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByRole('button', { name: 'Начать занятие' })).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: 'Заполнить посещаемость' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Домашнее задание' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Завершить занятие' })).not.toBeInTheDocument()
      // Cancel is only reachable through the "⋯" menu, never a plain button.
      expect(screen.queryByRole('button', { name: 'Отменить занятие' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Дополнительные действия' })).toBeInTheDocument()
    })

    it('starts the lesson when "Начать занятие" is clicked', async () => {
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

    it('offers "Отменить занятие" inside the "⋯" menu', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status: 'scheduled', can_start: true, can_cancel: true }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      const user = userEvent.setup()
      renderLessonDetail(7)

      await user.click(await screen.findByRole('button', { name: 'Дополнительные действия' }))
      expect(await screen.findByRole('menuitem', { name: 'Отменить занятие' })).toBeInTheDocument()
    })

    it('hides Start entirely when the backend says it is not allowed (not the owning teacher)', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status: 'scheduled', can_start: false, can_cancel: false }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByText('О занятии')).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: 'Начать занятие' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Дополнительные действия' })).not.toBeInTheDocument()
    })
  })

  describe('in-progress lesson', () => {
    function inProgressLesson(overrides: Parameters<typeof buildLesson>[0] = {}) {
      return buildLesson({
        id: 7,
        status: 'in_progress',
        can_start: false,
        can_cancel: true,
        ...overrides,
      })
    }

    it('shows the three workflow buttons and tucks cancel into the menu', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgressLesson({ can_complete: false }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByRole('button', { name: 'Заполнить посещаемость' })).toBeInTheDocument())
      expect(screen.getByRole('button', { name: 'Домашнее задание' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Завершить занятие' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Отменить занятие' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Дополнительные действия' })).toBeInTheDocument()
    })

    it('navigates to the attendance screen when "Заполнить посещаемость" is clicked', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgressLesson({ can_complete: false }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      const user = userEvent.setup()
      renderLessonDetail(7)

      await user.click(await screen.findByRole('button', { name: 'Заполнить посещаемость' }))
      expect(await screen.findByText('Attendance page')).toBeInTheDocument()
    })

    it('shows the progress checklist and a warning while completion is blocked', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        inProgressLesson({
          can_complete: false,
          attendance_completed: false,
          homework_added: false,
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
      expect(screen.getByText('Занятие начато')).toBeInTheDocument()
      expect(screen.getByText('Посещаемость не отмечена')).toBeInTheDocument()
      expect(screen.getByText('Домашнее задание не добавлено')).toBeInTheDocument()
      expect(screen.getByText(/Нельзя завершить занятие/)).toBeInTheDocument()
    })

    it('completes the lesson once requirements are satisfied', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        inProgressLesson({
          can_complete: true,
          attendance_completed: true,
          homework_added: false,
          homework_not_required: true,
          completion_requirements: [
            { key: 'attendance', label: 'Посещаемость отмечена', satisfied: true },
            { key: 'homework', label: 'Добавлено домашнее задание или отмечено «ДЗ не требуется»', satisfied: true },
          ],
          completion_progress: { satisfied: 2, total: 2, is_complete: true },
        }),
      )
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
      vi.mocked(lessonsApi.complete).mockResolvedValue(buildLesson({ id: 7, status: 'completed' }))

      const user = userEvent.setup()
      renderLessonDetail(7)

      const completeButton = await screen.findByRole('button', { name: 'Завершить занятие' })
      expect(completeButton).not.toBeDisabled()
      expect(screen.getByText('ДЗ не требуется')).toBeInTheDocument()
      await user.click(completeButton)

      await waitFor(() => expect(lessonsApi.complete).toHaveBeenCalledWith(7))
    })

    it('opens the homework screen when "Домашнее задание" is clicked and homework already exists', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgressLesson({ can_complete: false, homework_added: true }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([buildHomework({ id: 55, lesson: 7 })]))

      const user = userEvent.setup()
      renderLessonDetail(7)

      await user.click(await screen.findByRole('button', { name: 'Домашнее задание' }))
      expect(await screen.findByText('Homework detail page')).toBeInTheDocument()
    })

    it('opens the add-homework modal when "Домашнее задание" is clicked and none exists yet', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgressLesson({ can_complete: false, homework_added: false }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      const user = userEvent.setup()
      renderLessonDetail(7)

      await user.click(await screen.findByRole('button', { name: 'Домашнее задание' }))
      expect(await screen.findByRole('dialog', { name: 'Добавить домашнее задание' })).toBeInTheDocument()
    })

    it('cancels the lesson with a reason from the menu', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgressLesson({ can_complete: false }))
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
      vi.mocked(lessonsApi.cancel).mockResolvedValue(buildLesson({ id: 7, status: 'cancelled', cancellation_reason: 'Болезнь' }))

      const user = userEvent.setup()
      renderLessonDetail(7)

      await user.click(await screen.findByRole('button', { name: 'Дополнительные действия' }))
      await user.click(await screen.findByRole('menuitem', { name: 'Отменить занятие' }))

      const dialog = await screen.findByRole('dialog', { name: 'Отменить занятие' })
      await user.type(within(dialog).getByPlaceholderText(/тренер заболел/i), 'Болезнь')
      await user.click(within(dialog).getByRole('button', { name: 'Отменить занятие' }))

      await waitFor(() => expect(lessonsApi.cancel).toHaveBeenCalledWith(7, 'Болезнь'))
    })
  })

  describe('completed lesson', () => {
    it('shows only read-only view actions — never Start/Complete/Cancel, and never a separate results button', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        buildLesson({
          id: 7,
          status: 'completed',
          can_start: false,
          can_complete: false,
          can_cancel: false,
          homework_added: true,
          attendance_editable: false,
        }),
      )
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([buildHomework({ id: 55, lesson: 7 })]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByRole('button', { name: 'Посмотреть посещаемость' })).toBeInTheDocument())
      expect(screen.getByRole('button', { name: 'Посмотреть домашнее задание' })).toBeInTheDocument()
      // Results are reached from the homework card/detail, never as a
      // separate action on the completed lesson overview.
      expect(screen.queryByRole('button', { name: 'Посмотреть результаты' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Начать занятие' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Завершить занятие' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Отменить/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Дополнительные действия' })).not.toBeInTheDocument()
    })

    it('omits the homework view action when no homework was ever added', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        buildLesson({
          id: 7,
          status: 'completed',
          can_start: false,
          can_complete: false,
          can_cancel: false,
          homework_added: false,
          homework_not_required: true,
          attendance_editable: false,
        }),
      )
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByRole('button', { name: 'Посмотреть посещаемость' })).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: 'Посмотреть домашнее задание' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Посмотреть результаты' })).not.toBeInTheDocument()
    })

    it('shows the required read-only notice and status badge, never mixing terminology', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        buildLesson({ id: 7, status: 'completed', status_display: 'Проведено', can_start: false, can_complete: false, can_cancel: false, attendance_editable: false }),
      )
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      renderLessonDetail(7)

      await waitFor(() =>
        expect(
          screen.getByText('Занятие проведено и закрыто. Все данные сохранены. Редактирование недоступно.'),
        ).toBeInTheDocument(),
      )
      expect(screen.getByText('Проведено')).toBeInTheDocument()
      expect(screen.queryByText('Завершено')).not.toBeInTheDocument()
      expect(screen.queryByText('Completed')).not.toBeInTheDocument()
    })

    it('shows real, backend-calculated KPI values — never invented frontend stats', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        buildLesson({
          id: 7,
          status: 'completed',
          can_start: false,
          can_complete: false,
          can_cancel: false,
          homework_added: true,
          attendance_editable: false,
          attendance_summary: { total_students: 3, present: 3, absent: 0, late: 0, excused: 0, attendance_rate: 100 },
          homework_summary: { results_total: 3, checked: 3, pending: 0, average_score: 9.5 },
        }),
      )
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([buildHomework({ id: 55, lesson: 7 })]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByText('Итоги занятия')).toBeInTheDocument())
      expect(screen.getAllByText('3').length).toBeGreaterThan(0)
      expect(screen.getByText('100%')).toBeInTheDocument()
      expect(screen.getByText('3 из 3')).toBeInTheDocument()
      expect(screen.getByText('9.5 / 10')).toBeInTheDocument()
      // Attendance/homework read models come straight from the API, not a
      // second, ad-hoc roster fetch just for the completed-lesson page.
      expect(lessonsApi.getAttendanceRoster).not.toHaveBeenCalled()
    })
  })

  describe('cancelled lesson', () => {
    it('shows the cancellation reason and no action buttons', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(
        buildLesson({ id: 7, status: 'cancelled', can_start: false, can_complete: false, can_cancel: false, cancellation_reason: 'Праздник' }),
      )
      vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))

      renderLessonDetail(7)

      await waitFor(() => expect(screen.getByText(/Праздник/)).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: 'Начать занятие' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Завершить занятие' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Отменить/ })).not.toBeInTheDocument()
    })
  })
})
