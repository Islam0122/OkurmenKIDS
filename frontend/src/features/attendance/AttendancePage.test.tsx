import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AttendancePage } from '@/features/attendance/AttendancePage'
import { buildAttendanceRecord, buildLesson } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/lessons', () => ({
  lessonsApi: { get: vi.fn(), list: vi.fn(), getAttendanceRoster: vi.fn(), saveAttendance: vi.fn() },
}))

import { lessonsApi } from '@/api/lessons'

function renderAttendance(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/app/attendance" element={<AttendancePage />} />
    </Routes>,
    { route },
  )
}

describe('AttendancePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults every student to "Был" and bulk-saves the whole roster in one request', async () => {
    vi.mocked(lessonsApi.get).mockResolvedValue(buildLesson({ id: 7, group_name: 'Роботы-1' }))
    vi.mocked(lessonsApi.getAttendanceRoster).mockResolvedValue([
      buildAttendanceRecord({ student: 1, student_name: 'Иванов Пётр', status: null, id: null }),
      buildAttendanceRecord({ student: 2, student_name: 'Петров Иван', status: null, id: null }),
    ])
    vi.mocked(lessonsApi.saveAttendance).mockResolvedValue([])

    const user = userEvent.setup()
    renderAttendance('/app/attendance?lesson=7')

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
})
