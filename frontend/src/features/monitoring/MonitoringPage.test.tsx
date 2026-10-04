import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { monitoringApi } from '@/api/monitoring'
import { buildUser, paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { MonitoringAttempt, MonitoringAttemptDetail } from '@/types/monitoring'

import { MonitoringPage } from './MonitoringPage'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/monitoring', () => ({
  monitoringApi: {
    overview: vi.fn(), attempts: vi.fn(), attempt: vi.fn(), filters: vi.fn(),
    teachers: vi.fn(), groups: vi.fn(), group: vi.fn(), trainers: vi.fn(), trainer: vi.fn(),
  },
}))

const row: MonitoringAttempt = {
  id: 'a1', student_name: 'Айбек Асанов', student_id: 1, group: { id: 3, name: 'Python 12' },
  teacher: { id: 2, name: 'Тренер' }, session: { id: 's1', title: 'Python экзамен' },
  test: { id: 't1', title: 'Python', subject: 'Python' }, mode: 'exam', exam_mode: true,
  started_at: '2026-10-04T09:00:00Z', finished_at: null, expires_at: '2026-10-04T10:00:00Z',
  remaining_seconds: 1200, duration_seconds: null, answered: 4, question_total: 10, status: 'in_progress',
  score: null, passed: null, passing_score: 60, tab_switch_count: 2, fullscreen_exits: 1, violation_count: 3,
  max_tab_switches: 3, severity: 'warning', finish_reason: '',
}

const detail: MonitoringAttemptDetail = {
  ...row,
  events: [
    { id: 1, type: 'EXAM_STARTED', label: 'Экзамен начат', severity: 'info', timestamp: '2026-10-04T09:00:00Z', question: null, detail: '' },
    { id: 2, type: 'TAB_SWITCH', label: 'Переключение вкладки', severity: 'warning', timestamp: '2026-10-04T09:05:00Z', question: 4, detail: '' },
  ],
  violations: { TAB_SWITCH: 2, FULLSCREEN_EXIT: 1, COPY_ATTEMPT: 0 },
  questions: [],
}

describe('MonitoringPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(monitoringApi.overview).mockResolvedValue({
      active_exams: 1, active_trainers: 2, active_students: 1, completed: 5, passed: 3, failed: 2,
      expired: 0, terminated: 1, violations: 7, flagged_attempts: 2, average_score: 64,
    })
    vi.mocked(monitoringApi.attempts).mockResolvedValue(paginated([row]))
    vi.mocked(monitoringApi.attempt).mockResolvedValue(detail)
    vi.mocked(monitoringApi.filters).mockResolvedValue({ groups: [{ id: 3, name: 'Python 12' }], subjects: [], teachers: [], sessions: [], team_view: false })
  })

  it('shows backend numbers and live attempts, and opens the event timeline', async () => {
    mockRole.role = 'teacher'
    renderWithProviders(<MonitoringPage />, { route: '/app/monitoring' })

    await waitFor(() => expect(screen.getByText('Айбек Асанов')).toBeInTheDocument())
    expect(screen.getByText('4 / 10')).toBeInTheDocument()
    expect(screen.getByText('64%')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Тренеры' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Айбек Асанов' }))
    await waitFor(() => expect(screen.getByText('Переключение вкладки')).toBeInTheDocument())
    expect(monitoringApi.attempt).toHaveBeenCalledWith('a1')
  })

  it('filters are sent to the backend', async () => {
    mockRole.role = 'teacher'
    renderWithProviders(<MonitoringPage />, { route: '/app/monitoring' })
    await waitFor(() => expect(screen.getByText('Айбек Асанов')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Статус'), { target: { value: 'terminated' } })
    await waitFor(() => expect(monitoringApi.attempts).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'terminated', page: 1 })))
  })

  it('gives a Team Lead the teachers tab', async () => {
    mockRole.role = 'team_lead'
    renderWithProviders(<MonitoringPage />, { route: '/app/monitoring' })
    expect(await screen.findByRole('tab', { name: 'Тренеры' })).toBeInTheDocument()
  })
})
