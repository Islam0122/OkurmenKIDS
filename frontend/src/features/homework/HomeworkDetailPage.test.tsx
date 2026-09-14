import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomeworkDetailPage } from '@/features/homework/HomeworkDetailPage'
import { buildHomework, buildHomeworkResult } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/homework', () => ({
  homeworkApi: { list: vi.fn(), get: vi.fn(), getResultsRoster: vi.fn(), saveResults: vi.fn() },
}))

import { homeworkApi } from '@/api/homework'

function renderHomeworkDetail(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/homework" element={<div>Homework list page</div>} />
      <Route path="/app/homework/:id" element={<HomeworkDetailPage />} />
      <Route path="/app/lessons/:id" element={<div>Lesson detail page</div>} />
    </Routes>,
    { route },
  )
}

describe('HomeworkDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('grades a student and bulk-saves the roster through the results endpoint', async () => {
    vi.mocked(homeworkApi.get).mockResolvedValue(buildHomework({ id: 55, title: 'Собрать простого робота' }))
    vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
      buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр', status: 'not_submitted', score: null }),
    ])
    vi.mocked(homeworkApi.saveResults).mockResolvedValue([])

    const user = userEvent.setup()
    renderHomeworkDetail('/app/homework/55')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())

    const row = screen.getByText('Иванов Пётр').closest('li') as HTMLElement
    await user.click(within(row).getByRole('radio', { name: 'Проверено' }))
    await user.type(within(row).getByLabelText(/Балл/), '9')
    await user.click(screen.getByRole('button', { name: 'Сохранить результаты' }))

    await waitFor(() =>
      expect(homeworkApi.saveResults).toHaveBeenCalledWith(55, [
        { student: 1, status: 'checked', score: 9, comment: '' },
      ]),
    )
  })

  it('never lets the score exceed 10, even if the teacher types a larger number', async () => {
    vi.mocked(homeworkApi.get).mockResolvedValue(buildHomework({ id: 55 }))
    vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
      buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр' }),
    ])
    vi.mocked(homeworkApi.saveResults).mockResolvedValue([])

    const user = userEvent.setup()
    renderHomeworkDetail('/app/homework/55')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    const row = screen.getByText('Иванов Пётр').closest('li') as HTMLElement
    const scoreInput = within(row).getByLabelText(/Балл/) as HTMLInputElement

    await user.type(scoreInput, '55')

    expect(scoreInput.value).toBe('10')
  })

  it('returns to the exact Lesson Detail page it was opened from after a successful save', async () => {
    vi.mocked(homeworkApi.get).mockResolvedValue(buildHomework({ id: 55, lesson: 7 }))
    vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
      buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр' }),
    ])
    vi.mocked(homeworkApi.saveResults).mockResolvedValue([])

    const user = userEvent.setup()
    renderHomeworkDetail('/app/homework/55?returnTo=%2Fapp%2Flessons%2F7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить результаты' }))

    expect(await screen.findByText('Результаты успешно сохранены')).toBeInTheDocument()
    expect(await screen.findByText('Lesson detail page')).toBeInTheDocument()
  })

  it('falls back to the homework list when opened directly with no returnTo', async () => {
    vi.mocked(homeworkApi.get).mockResolvedValue(buildHomework({ id: 55 }))
    vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
      buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр' }),
    ])
    vi.mocked(homeworkApi.saveResults).mockResolvedValue([])

    const user = userEvent.setup()
    renderHomeworkDetail('/app/homework/55')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить результаты' }))

    expect(await screen.findByText('Homework list page')).toBeInTheDocument()
    expect(screen.queryByText('Lesson detail page')).not.toBeInTheDocument()
  })

  it('never follows an external returnTo — falls back to the homework list instead', async () => {
    vi.mocked(homeworkApi.get).mockResolvedValue(buildHomework({ id: 55 }))
    vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
      buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр' }),
    ])
    vi.mocked(homeworkApi.saveResults).mockResolvedValue([])

    const user = userEvent.setup()
    renderHomeworkDetail(`/app/homework/55?returnTo=${encodeURIComponent('https://evil.com')}`)

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить результаты' }))

    expect(await screen.findByText('Homework list page')).toBeInTheDocument()
  })

  it('shows an error toast and stays put when saving fails', async () => {
    vi.mocked(homeworkApi.get).mockResolvedValue(buildHomework({ id: 55 }))
    vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
      buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр' }),
    ])
    vi.mocked(homeworkApi.saveResults).mockRejectedValue(new Error('network down'))

    const user = userEvent.setup()
    renderHomeworkDetail('/app/homework/55?returnTo=%2Fapp%2Flessons%2F7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить результаты' }))

    expect(await screen.findByText('Не удалось сохранить результаты')).toBeInTheDocument()
    expect(screen.queryByText('Lesson detail page')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сохранить результаты' })).toBeInTheDocument()
  })

  describe('completed lesson', () => {
    it('hides the Save button and disables every control when results are not editable', async () => {
      vi.mocked(homeworkApi.get).mockResolvedValue(
        buildHomework({ id: 55, lesson_status: 'completed', results_editable: false }),
      )
      vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
        buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр', status: 'checked', score: 8 }),
      ])

      renderHomeworkDetail('/app/homework/55')

      await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: 'Сохранить результаты' })).not.toBeInTheDocument()
      expect(screen.getByText('Только просмотр')).toBeInTheDocument()

      const row = screen.getByText('Иванов Пётр').closest('li') as HTMLElement
      for (const radio of within(row).getAllByRole('radio')) {
        expect(radio).toBeDisabled()
      }
      expect(within(row).getByLabelText(/Балл/)).toBeDisabled()
    })

    it('never calls saveResults since there is no way to trigger it', async () => {
      vi.mocked(homeworkApi.get).mockResolvedValue(
        buildHomework({ id: 55, lesson_status: 'completed', results_editable: false }),
      )
      vi.mocked(homeworkApi.getResultsRoster).mockResolvedValue([
        buildHomeworkResult({ student: 1, student_name: 'Иванов Пётр', status: 'checked', score: 8 }),
      ])

      renderHomeworkDetail('/app/homework/55')

      await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
      expect(homeworkApi.saveResults).not.toHaveBeenCalled()
    })
  })
})
