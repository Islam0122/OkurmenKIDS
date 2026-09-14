import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AttendancePage } from '@/features/attendance/AttendancePage'
import { buildAttendanceRecord, buildLesson, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/lessons', () => ({
  lessonsApi: { get: vi.fn(), list: vi.fn(), getAttendanceRoster: vi.fn(), saveAttendance: vi.fn() },
}))

import { lessonsApi } from '@/api/lessons'

function renderAttendance(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/attendance" element={<AttendancePage />} />
      <Route path="/app/lessons/:id" element={<div>Lesson detail page</div>} />
    </Routes>,
    { route },
  )
}

describe('AttendancePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(lessonsApi.list).mockResolvedValue(paginated([]))
  })

  it('defaults every student to "Был" and bulk-saves the whole roster in one request', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, group_name: 'Роботы-1' }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: null, id: null }),
      buildAttendanceRecord({ student: 2, student_name: 'Петров Иван', status: null, id: null }),
    ])
    vi.mocked(lessonsApi.saveAttendance).mockResolvedValue([])

    const user = userEvent.setup()
    renderAttendance('/app/attendance?lesson=7&returnTo=%2Fapp%2Flessons%2F7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())

    // Mark the second student absent, first one stays on the fast-path default ("Был").
    const secondStudentRow = screen.getByText('Петров Иван').closest('li') as HTMLElement
    await user.click(within(secondStudentRow).getByRole('radio', { name: 'Не был' }))

    await user.click(screen.getByRole('button', { name: 'Сохранить посещаемость' }))

    await waitFor(() =>
      expect(lessonsApi.saveAttendance).toHaveBeenCalledWith(7, [
        { student: 1, status: 'present' },
        { student: 2, status: 'absent' },
      ]),
    )
  })

  it('returns to the exact Lesson Detail page it was opened from after a successful save', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7 }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: 'present' }),
    ])
    vi.mocked(lessonsApi.saveAttendance).mockResolvedValue([])

    const user = userEvent.setup()
    renderAttendance('/app/attendance?lesson=7&returnTo=%2Fapp%2Flessons%2F7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить посещаемость' }))

    expect(await screen.findByText('Посещаемость успешно сохранена')).toBeInTheDocument()
    expect(await screen.findByText('Lesson detail page')).toBeInTheDocument()
  })

  it('falls back to the attendance list when no returnTo was supplied', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7 }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: 'present' }),
    ])
    vi.mocked(lessonsApi.saveAttendance).mockResolvedValue([])

    const user = userEvent.setup()
    renderAttendance('/app/attendance?lesson=7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить посещаемость' }))

    // Landed back on the general attendance screen (the lesson picker),
    // never on a Lesson Detail page it was never told about.
    await waitFor(() => expect(screen.getByText('Посещаемость')).toBeInTheDocument())
    expect(screen.queryByText('Lesson detail page')).not.toBeInTheDocument()
  })

  it('never follows an external returnTo — falls back to the attendance list instead', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7 }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: 'present' }),
    ])
    vi.mocked(lessonsApi.saveAttendance).mockResolvedValue([])

    const user = userEvent.setup()
    renderAttendance(`/app/attendance?lesson=7&returnTo=${encodeURIComponent('https://evil.com')}`)

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить посещаемость' }))

    await waitFor(() => expect(screen.getByText('Посещаемость')).toBeInTheDocument())
    expect(screen.queryByText('Lesson detail page')).not.toBeInTheDocument()
  })

  it('becomes read-only once the lesson is completed — no save button, no editable controls', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, status: 'completed', attendance_editable: false }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: 'present' }),
    ])

    renderAttendance('/app/attendance?lesson=7&returnTo=%2Fapp%2Flessons%2F7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Сохранить посещаемость' })).not.toBeInTheDocument()
    expect(screen.getByText(/больше нельзя редактировать/)).toBeInTheDocument()
    const row = screen.getByText('Иванов Пётр').closest('li') as HTMLElement
    expect(within(row).getByRole('radio', { name: 'Был' })).toBeDisabled()
  })

  it('shows an error toast and stays put when saving fails', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7 }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: 'present' }),
    ])
    vi.mocked(lessonsApi.saveAttendance).mockRejectedValue(new Error('network down'))

    const user = userEvent.setup()
    renderAttendance('/app/attendance?lesson=7&returnTo=%2Fapp%2Flessons%2F7')

    await waitFor(() => expect(screen.getByText('Иванов Пётр')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Сохранить посещаемость' }))

    expect(await screen.findByText('Не удалось сохранить посещаемость')).toBeInTheDocument()
    expect(screen.queryByText('Lesson detail page')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сохранить посещаемость' })).toBeInTheDocument()
  })
})
