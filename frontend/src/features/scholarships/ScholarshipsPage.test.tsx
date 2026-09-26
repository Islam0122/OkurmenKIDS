import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ScholarshipsPage } from '@/features/scholarships/ScholarshipsPage'
import { buildUser, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/scholarships', () => ({
  scholarshipsApi: {
    periods: vi.fn(),
    ranking: vi.fn(),
    analytics: vi.fn(),
    recalculate: vi.fn(),
    approve: vi.fn(),
    requiredFeedback: vi.fn(),
    createFeedback: vi.fn(),
    updateFeedback: vi.fn(),
  },
}))

import { scholarshipsApi } from '@/api/scholarships'

const PERIOD = {
  id: 7,
  award_day: 1,
  period_start: '2026-09-01',
  period_end: '2026-09-30',
  evaluation_date: '2026-10-01',
  status: 'draft' as const,
}

describe('ScholarshipsPage — trainer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'teacher'
    vi.mocked(scholarshipsApi.periods).mockResolvedValue(paginated([PERIOD]))
    vi.mocked(scholarshipsApi.requiredFeedback).mockResolvedValue({
      period: PERIOD,
      total: 1,
      missing: 1,
      items: [{ student: 3, student_name: 'Islam Test', subject: 2, subject_name: 'Python', is_submitted: false, feedback: null }],
    })
    vi.mocked(scholarshipsApi.createFeedback).mockResolvedValue({} as never)
  })

  it('lists students awaiting feedback and submits a complete assessment', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ScholarshipsPage />, { route: '/app/scholarships' })

    await waitFor(() => expect(screen.getByText('Islam Test')).toBeInTheDocument())
    expect(screen.getByText('Нет оценки')).toBeInTheDocument()
    expect(scholarshipsApi.ranking).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Оценить' }))
    const save = screen.getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled() // nothing is pre-filled

    for (const label of ['Прогресс', 'Активность на занятиях', 'Дисциплина', 'Понимание материала']) {
      const group = screen.getByRole('radiogroup', { name: label })
      await user.click(group.querySelectorAll('button')[3]) // score 4
    }
    expect(save).toBeEnabled()
    await user.click(save)

    await waitFor(() =>
      expect(scholarshipsApi.createFeedback).toHaveBeenCalledWith({
        period: 7,
        student: 3,
        subject: 2,
        progress: 4,
        participation: 4,
        discipline: 4,
        understanding: 4,
        comment: '',
      }),
    )
  })
})

describe('ScholarshipsPage — admin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'admin'
    vi.mocked(scholarshipsApi.periods).mockResolvedValue(paginated([{ ...PERIOD, max_recipients: 20 }]))
    vi.mocked(scholarshipsApi.analytics).mockResolvedValue({
      total_evaluated: 3,
      total_eligible: 2,
      total_recipients: 2,
      max_recipients: 20,
      incomplete_data: 1,
      averages: { overall: '88.50', attendance: '90.00', homework: '85.00', feedback: '90.00' },
    })
    vi.mocked(scholarshipsApi.ranking).mockResolvedValue(
      paginated([
        {
          id: 1, period: 7, student: 3, student_name: 'Islam Test', group_name: 'Prog SOFT 1', course_name: 'Prog',
          enrollment_date: '2026-01-10', overall_score: '93.33', attendance_score: '95.00', homework_score: '90.00',
          feedback_score: '95.00', lessons_count: 12, subjects_count: 3, rank: 1, eligibility_status: 'eligible',
          ineligibility_reason: '', award_status: 'pending',
        },
        {
          id: 2, period: 7, student: 4, student_name: 'Aida Test', group_name: 'Prog SOFT 1', course_name: 'Prog',
          enrollment_date: '2026-01-10', overall_score: '70.00', attendance_score: '70.00', homework_score: null,
          feedback_score: '0.00', lessons_count: 4, subjects_count: 1, rank: null, eligibility_status: 'incomplete_data',
          ineligibility_reason: 'Нет оценки тренера: English.', award_status: null,
        },
      ]),
    )
  })

  it('shows the ranking with eligibility and award status', async () => {
    renderWithProviders(<ScholarshipsPage />, { route: '/app/scholarships' })

    await waitFor(() => expect(screen.getByText('93.33')).toBeInTheDocument())
    expect(screen.getByText('Неполные данные', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Ожидает')).toBeInTheDocument()
    expect(screen.getByText('2 / 20')).toBeInTheDocument()
    expect(scholarshipsApi.requiredFeedback).not.toHaveBeenCalled()
  })
})
