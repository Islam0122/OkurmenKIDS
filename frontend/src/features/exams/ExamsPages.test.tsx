import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExamDetailPage } from '@/features/exams/ExamDetailPage'
import { ExamsListPage } from '@/features/exams/ExamsListPage'
import { LiveExamsWidget } from '@/features/exams/LiveExamsWidget'
import { buildExamParticipant, buildExamSession } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'

vi.mock('@/api/exams', () => ({
  examsApi: { list: vi.fn(), get: vi.fn(), participants: vi.fn(), participantResult: vi.fn() },
}))

import { examsApi } from '@/api/exams'

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

describe('ExamsListPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a live session with its group, time and progress breakdown', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([buildExamSession()]))
    renderWithProviders(<ExamsListPage />, { route: '/app/exams' })

    const card = (await screen.findByText('Python — Итоговый экзамен')).closest('article') as HTMLElement
    expect(within(card).getByText('Идёт сейчас')).toBeInTheDocument()
    expect(within(card).getByText('Python-01')).toBeInTheDocument()
    expect(within(card).getByText('18 студентов')).toBeInTheDocument()
    expect(within(card).getByText(/14 завершили/)).toBeInTheDocument()
    expect(within(card).getByText(/2 проходят/)).toBeInTheDocument()
    expect(within(card).getByText(/2 не начали/)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Открыть' })).toHaveAttribute('href', '/app/exams/session-1')
  })

  it('filters by status through the API', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([]))
    const user = userEvent.setup()
    renderWithProviders(<ExamsListPage />, { route: '/app/exams' })
    await screen.findByText('Экзаменов нет')

    await user.click(screen.getByRole('radio', { name: 'Сейчас проходят' }))
    await waitFor(() => expect(examsApi.list).toHaveBeenLastCalledWith({ status: 'live', page: 1 }))
    expect(screen.getByText('Сейчас ни одна из ваших групп не проходит экзамен.')).toBeInTheDocument()
  })
})

function renderDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/app/exams" element={<div>Exams list</div>} />
      <Route path="/app/exams/:id" element={<ExamDetailPage />} />
    </Routes>,
    { route: '/app/exams/session-1' },
  )
}

describe('ExamDetailPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows KPIs and each student’s progress, but no score while the exam is running', async () => {
    vi.mocked(examsApi.participants).mockResolvedValue({
      session: buildExamSession(),
      server_time: '2026-10-02T08:40:00Z',
      participants: [
        buildExamParticipant(),
        buildExamParticipant({
          id: 'p2', student: { id: 2, name: 'Айбек Асанов' }, status: 'completed', status_label: 'Завершил',
          answered_count: 20, current_question: 20, progress_percent: 100, score: 85, result_available: true,
          finished_at: '2026-10-02T08:47:00Z', duration_seconds: 2833,
        }),
        buildExamParticipant({
          id: 'p3', student: { id: 3, name: 'Мария Ким' }, status: 'not_started', status_label: 'Не начал',
          answered_count: 0, current_question: 0, question_total: 0, progress_percent: 0, started_at: null,
          last_seen_at: null, duration_seconds: null,
        }),
        buildExamParticipant({ id: 'p4', student: { id: 4, name: 'Нурлан Т.' }, status: 'disconnected', status_label: 'Нет соединения' }),
      ],
    })
    renderDetail()

    await screen.findByRole('heading', { name: 'Python — Итоговый экзамен' })
    expect(screen.getByText('Всего студентов')).toBeInTheDocument()
    expect(screen.getByText('Проходят сейчас')).toBeInTheDocument()
    expect(screen.getAllByText('Проходит экзамен').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Нет соединения').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Не начал').length).toBeGreaterThan(0)

    const table = screen.getByRole('table')
    const islamRow = within(table).getByText('Ислам Дуйшобаев').closest('tr') as HTMLElement
    expect(within(islamRow).getByText('14 / 20')).toBeInTheDocument()
    expect(within(islamRow).getByText('Вопрос 15')).toBeInTheDocument()
    expect(within(islamRow).queryByText(/%$/, { selector: 'button' })).not.toBeInTheDocument()

    const doneRow = within(table).getByText('Айбек Асанов').closest('tr') as HTMLElement
    expect(within(doneRow).getByRole('button', { name: '85%' })).toBeInTheDocument()
    expect(within(doneRow).getByText('47:13')).toBeInTheDocument()
  })

  it('opens a finished student’s detailed result', async () => {
    vi.mocked(examsApi.participants).mockResolvedValue({
      session: buildExamSession(),
      server_time: '2026-10-02T08:40:00Z',
      participants: [
        buildExamParticipant({ id: 'p2', status: 'completed', status_label: 'Завершил', score: 85, result_available: true }),
      ],
    })
    vi.mocked(examsApi.participantResult).mockResolvedValue({
      student: { id: 1, name: 'Ислам Дуйшобаев' },
      score: 85,
      finished_at: '2026-10-02T08:47:00Z',
      duration_seconds: 2833,
      passing_score: 70,
      questions: [
        { number: 1, text: 'Какой язык для backend?', image_url: null, question_type: 'single_choice', points: 1,
          status: 'wrong', selected: ['HTML'], answer_text: '', correct: ['Python'] },
      ],
    })
    const user = userEvent.setup()
    renderDetail()

    await user.click(within(await screen.findByRole('table')).getByRole('button', { name: '85%' }))
    expect(await screen.findByText('1. Какой язык для backend?')).toBeInTheDocument()
    expect(screen.getByText('Правильно: Python')).toBeInTheDocument()
    expect(examsApi.participantResult).toHaveBeenCalledWith('session-1', 'p2')
  })

  it('shows a not-found state for a session the backend refuses (another group’s)', async () => {
    vi.mocked(examsApi.participants).mockRejectedValue(new Error('404'))
    renderDetail()
    expect(await screen.findByText('Экзамен не найден')).toBeInTheDocument()
  })
})

describe('LiveExamsWidget', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists exams running now with the group’s progress', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([buildExamSession()]))
    renderWithProviders(<LiveExamsWidget />)
    expect(await screen.findByText('1 экзамен идёт сейчас')).toBeInTheDocument()
    expect(screen.getByText('14 / 18 завершили')).toBeInTheDocument()
    expect(examsApi.list).toHaveBeenCalledWith({ status: 'live' })
  })

  it('renders nothing when no exam is running', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([]))
    renderWithProviders(<LiveExamsWidget />)
    await waitFor(() => expect(examsApi.list).toHaveBeenCalled())
    expect(screen.queryByText(/сейчас$/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Все экзамены' })).not.toBeInTheDocument()
  })
})
