import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { monitoringApi } from '@/api/monitoring'
import { paginated } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { MonitoringAttempt, MonitoringAttemptDetail, ResultsSummary } from '@/types/monitoring'

import { ResultsTable, StudentResultsTable, ResultsOverview } from './resultsUi'

vi.mock('@/api/monitoring', () => ({
  monitoringApi: {
    results: vi.fn(), resultsSummary: vi.fn(), resultStudents: vi.fn(), resultBreakdown: vi.fn(), exportResults: vi.fn(),
    attempt: vi.fn(),
  },
}))

const row: MonitoringAttempt = {
  id: 'r1', student_name: 'Айбек Асанов', student_id: 7, group: { id: 3, name: 'Python 12' }, teacher: { id: 2, name: 'Тренер А' },
  session: { id: 's1', title: 'Python Month 1' }, test: { id: 't1', title: 'Python Month 1', subject: 'Python' }, mode: 'exam',
  exam_mode: true, started_at: '2026-10-04T09:00:00Z', finished_at: '2026-10-04T09:20:00Z', expires_at: null, remaining_seconds: null,
  duration_seconds: 1200, answered: 20, question_total: 20, status: 'completed', score: 85, passed: true, passing_score: 60,
  tab_switch_count: 0, fullscreen_exits: 0, violation_count: 0, max_tab_switches: null, severity: 'normal', finish_reason: 'submitted',
  correct_count: 17, incorrect_count: 3, attempt_no: 2,
}
const detail: MonitoringAttemptDetail = {
  ...row, events: [], violations: {},
  questions: [
    { number: 1, question_id: 'q1', text: 'Backend?', full_text: 'Backend?', status: 'correct', selected: ['Python'], correct: ['Python'], answer_text: '', answered_at: '2026-10-04T09:01:00Z' },
    { number: 2, question_id: 'q2', text: 'list.append?', full_text: 'list.append?', status: 'wrong', selected: ['extend'], correct: ['append'], answer_text: '', answered_at: null },
  ],
}
const summary: ResultsSummary = {
  attempts: 124, students_tested: 42, groups: 3, tests: 5, passed: 94, failed: 30, pass_rate: 75.8, failed_rate: 24.2,
  average_score: 82.4, best_score: 100, lowest_score: 31, average_correct: 16.4, average_questions: 20,
  best_student: { id: 7, name: 'Айбек Асанов', average_score: 96, attempts: 4 }, best_group: { id: 3, name: 'Python 12', average_score: 88, attempts: 40 },
  dynamics: [],
}

describe('test results UI', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows results with correct / incorrect answers and opens every answer in «Подробнее»', async () => {
    vi.mocked(monitoringApi.results).mockResolvedValue(paginated([row]))
    vi.mocked(monitoringApi.attempt).mockResolvedValue(detail)
    renderWithProviders(<ResultsTable filters={{ student: '7' }} />)

    expect(await screen.findByText('Айбек Асанов')).toBeInTheDocument()
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('Сдал')).toBeInTheDocument()
    expect(monitoringApi.results).toHaveBeenCalledWith(expect.objectContaining({ student: '7', page: 1 }))

    fireEvent.click(screen.getByRole('button', { name: 'Подробнее' }))
    const answers = await screen.findByRole('heading', { name: 'Ответы' })
    const section = answers.closest('section') as HTMLElement
    expect(within(section).getByText('extend')).toBeInTheDocument()
    expect(within(section).getByText('append')).toBeInTheDocument()
    fireEvent.click(within(section).getByLabelText(/Только ошибки/))
    expect(within(section).queryByText('Backend?', { exact: false })).not.toBeInTheDocument()
  })

  it('says so when there are no results yet', async () => {
    vi.mocked(monitoringApi.results).mockResolvedValue(paginated([]))
    renderWithProviders(<ResultsTable filters={{ group: '3' }} />)
    expect(await screen.findByText('Азырынча тесттин жыйынтыгы жок')).toBeInTheDocument()
  })

  it('teacher overview: backend numbers, best student and group', async () => {
    vi.mocked(monitoringApi.resultsSummary).mockResolvedValue(summary)
    renderWithProviders(<ResultsOverview filters={{ teacher: '2' }} />)
    expect(await screen.findByText('82.4%')).toBeInTheDocument()
    expect(screen.getByText('75.8%')).toBeInTheDocument()
    expect(screen.getByText('Айбек Асанов')).toBeInTheDocument()
    expect(screen.getByText('Python 12')).toBeInTheDocument()
    expect(screen.getByText('правильных в среднем: 16.4 / 20')).toBeInTheDocument()
  })

  it('per-student table of a group', async () => {
    vi.mocked(monitoringApi.resultStudents).mockResolvedValue([
      { student: { id: 7, name: 'Айбек Асанов' }, attempts: 3, average_score: 80, best_score: 92, last_score: 67, last_passed: false, last_at: '2026-10-04T09:20:00Z' },
    ])
    renderWithProviders(<StudentResultsTable filters={{ group: '3' }} />)
    await waitFor(() => expect(screen.getByText('92%')).toBeInTheDocument())
    expect(screen.getByText('Не сдал')).toBeInTheDocument()
  })
})
