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

function renderHomeworkDetail(id = 55) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/homework/:id" element={<HomeworkDetailPage />} />
      <Route path="/app/lessons/:id" element={<div>Lesson page</div>} />
    </Routes>,
    { route: `/app/homework/${id}` },
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
    renderHomeworkDetail(55)

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
    renderHomeworkDetail(55)

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    const row = screen.getByText('Иванов Пётр').closest('li') as HTMLElement
    const scoreInput = within(row).getByLabelText(/Балл/) as HTMLInputElement

    await user.type(scoreInput, '55')

    expect(scoreInput.value).toBe('10')
  })
})
