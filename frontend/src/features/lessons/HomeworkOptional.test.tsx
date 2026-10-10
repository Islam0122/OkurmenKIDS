import { Route, Routes } from 'react-router-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LessonDetailPage } from '@/features/lessons/LessonDetailPage'
import { getLessonActionPlan, getPrimaryCardAction } from '@/features/lessons/lessonActions'
import { buildHomework, buildLesson, buildUser, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { Lesson } from '@/types/academy'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: 'teacher' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/lessons', () => ({
  lessonsApi: { get: vi.fn(), getAttendanceRoster: vi.fn(), list: vi.fn(), saveAttendance: vi.fn(), start: vi.fn(), complete: vi.fn(), cancel: vi.fn(), setHomeworkNotRequired: vi.fn() },
}))
vi.mock('@/api/homework', () => ({
  homeworkApi: { list: vi.fn(), get: vi.fn(), getResultsRoster: vi.fn(), saveResults: vi.fn(), create: vi.fn() },
}))

import { homeworkApi } from '@/api/homework'
import { lessonsApi } from '@/api/lessons'

function inProgress(overrides: Partial<Lesson> = {}): Lesson {
  return buildLesson({ id: 7, status: 'in_progress', status_display: 'Идёт', can_start: false, can_cancel: true, ...overrides })
}

/** What the backend sends for a lesson whose plan declares no homework and that has none. */
const NO_HOMEWORK: Partial<Lesson> = {
  homework_expected: false,
  homework_added: false,
  homework_not_required: false,
  completion_requirements: [{ key: 'attendance', label: 'Посещаемость отмечена', satisfied: true }],
  completion_progress: { satisfied: 1, total: 1, is_complete: true },
}

function render() {
  return renderWithProviders(
    <Routes>
      <Route path="/app/lessons/:id" element={<LessonDetailPage />} />
      <Route path="/app/homework/:id" element={<div>Homework detail page</div>} />
    </Routes>,
    { route: '/app/lessons/7' },
  )
}

describe('Homework step — only for lessons that have homework', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([])
  })

  describe('no homework (none added, none in the lesson plan)', () => {
    it('hides the homework button, status and «ДЗ не требуется»; completion only needs attendance', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgress({ ...NO_HOMEWORK, attendance_completed: true, can_complete: true }))
      vi.mocked(lessonsApi.complete).mockResolvedValue(inProgress({ ...NO_HOMEWORK, status: 'completed' }))
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
      const user = userEvent.setup()
      render()

      const complete = await screen.findByRole('button', { name: 'Завершить занятие' })
      expect(screen.getByRole('button', { name: 'Заполнить посещаемость' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Домашнее задание' })).not.toBeInTheDocument()
      expect(screen.queryByText('Домашнее задание не добавлено')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Отметить «ДЗ не требуется»' })).not.toBeInTheDocument()
      expect(screen.queryByText(/Нельзя завершить занятие/)).not.toBeInTheDocument()
      expect(screen.getByText('Готово к завершению')).toBeInTheDocument()

      expect(complete).toBeEnabled()
      await user.click(complete)
      await waitFor(() => expect(lessonsApi.complete).toHaveBeenCalledWith(7))
      expect(lessonsApi.setHomeworkNotRequired).not.toHaveBeenCalled()
    })

    it('still blocks completion on attendance alone', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgress({
        ...NO_HOMEWORK, attendance_completed: false, can_complete: false,
        completion_requirements: [{ key: 'attendance', label: 'Посещаемость отмечена', satisfied: false }],
        completion_progress: { satisfied: 0, total: 1, is_complete: false },
      }))
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
      render()

      expect(await screen.findByRole('button', { name: 'Завершить занятие' })).toBeDisabled()
      expect(screen.getByText('Нельзя завершить занятие: Посещаемость отмечена.')).toBeInTheDocument()
      expect(screen.queryByText(/домашнее задание/i)).not.toBeInTheDocument()
    })

    it('a completed lesson shows no homework card or tile', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status: 'completed', status_display: 'Проведён', ...NO_HOMEWORK, homework_summary: null }))
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
      render()

      expect(await screen.findByText('Результаты занятия')).toBeInTheDocument()
      expect(screen.queryByText('Домашнее задание')).not.toBeInTheDocument()
      expect(screen.queryByText('ДЗ не было добавлено.')).not.toBeInTheDocument()
    })

    it('the lesson card goes straight from attendance to completion', () => {
      const lesson = inProgress({ ...NO_HOMEWORK, attendance_completed: true })
      expect(getPrimaryCardAction(lesson).key).toBe('complete')
      expect(getLessonActionPlan(lesson).primary.map((a) => a.key)).toEqual(['attendance', 'complete'])
    })
  })

  describe('homework exists — exactly as before', () => {
    it('keeps the homework button, opens the homework, keeps the checklist line', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgress({ homework_expected: true, homework_added: true, attendance_completed: true, can_complete: true }))
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([buildHomework({ id: 99, lesson: 7 })]))
      const user = userEvent.setup()
      render()

      await user.click(await screen.findByRole('button', { name: 'Домашнее задание' }))
      expect(await screen.findByText('Homework detail page')).toBeInTheDocument()
    })

    it('declared but not added: button, «не добавлено» and «ДЗ не требуется» stay', async () => {
      vi.mocked(lessonsApi.get).mockResolvedValue(inProgress({ homework_expected: true, homework_added: false, attendance_completed: true, can_complete: false }))
      vi.mocked(homeworkApi.list).mockResolvedValue(paginated([]))
      render()

      expect(await screen.findByRole('button', { name: 'Домашнее задание' })).toBeInTheDocument()
      expect(screen.getByText('Домашнее задание не добавлено')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Отметить «ДЗ не требуется»' })).toBeInTheDocument()
      expect(getPrimaryCardAction(inProgress({ homework_expected: true, attendance_completed: true })).key).toBe('homework')
    })
  })
})
