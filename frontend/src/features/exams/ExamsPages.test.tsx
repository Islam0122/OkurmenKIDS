import { Route, Routes } from 'react-router-dom'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExamDetailPage } from '@/features/exams/ExamDetailPage'
import { ExamsListPage } from '@/features/exams/ExamsListPage'
import { LiveExamsWidget } from '@/features/exams/LiveExamsWidget'
import { testPage } from '@/features/exams/MyResults'
import {
  buildExamParticipant,
  buildExamSession,
  buildGroup,
  buildGroupTeacherSummary,
  buildSubject,
  buildUser,
} from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { MyAttempt } from '@/types/exams'

const mockRole = vi.hoisted(() => ({ role: 'teacher' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('@/api/exams', () => ({
  examsApi: {
    list: vi.fn(),
    get: vi.fn(),
    participants: vi.fn(),
    participantResult: vi.fn(),
    create: vi.fn(),
    start: vi.fn(),
    take: vi.fn(),
    myAttempts: vi.fn(),
    tests: vi.fn(),
  },
}))
vi.mock('@/api/groups', () => ({ groupsApi: { list: vi.fn(), get: vi.fn() } }))

import { examsApi } from '@/api/exams'
import { groupsApi } from '@/api/groups'

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

describe('ExamsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'teacher'
  })

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
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'teacher'
  })

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

function myAttempt(overrides: Partial<MyAttempt> = {}): MyAttempt {
  return {
    id: 'attempt-1',
    session: { id: 'session-1', title: 'Python — Итоговый экзамен', group: { id: 3, name: 'Python PRO — группа 3' } },
    test: { id: 'test-1', title: 'Python Basics #4', passing_score: 70 },
    status: 'finished',
    status_label: 'Завершена',
    started_at: '2026-10-04T08:00:00Z',
    finished_at: '2026-10-04T08:40:00Z',
    duration_seconds: 2400,
    score: { earned: 18, possible: 20, percent: 90, correct: 18, wrong: 2, pending: 0, unanswered: 0, total_questions: 20, passed: true },
    take_url: null,
    result_url: 'https://api.example/exam/a/attempt-1/result/?t=signed',
    ...overrides,
  }
}

describe('Team Lead — Сессии', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'team_lead'
    vi.mocked(examsApi.myAttempts).mockResolvedValue([])
  })

  it('sees «Сессии» with «Создать сессию»', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([buildExamSession()]))
    renderWithProviders(<ExamsListPage />, { route: '/app/exams' })
    expect(await screen.findByRole('heading', { name: 'Сессии' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать сессию' })).toBeInTheDocument()
    const card = (await screen.findByText('Python — Итоговый экзамен')).closest('article') as HTMLElement
    expect(within(card).getByText(/Тренер: Айгуль Сатыбалдиева/)).toBeInTheDocument()
  })

  it('creates a session for a group: test, group, date and time', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([]))
    vi.mocked(examsApi.tests).mockResolvedValue(page([
      { id: 'test-4', title: 'Python Basics #4', subject_name: 'Python', level_display: 'Начальный', status: 'active',
        status_display: 'Активен', time_limit_minutes: 60, passing_score: 70, question_count: 20, attempt_count: 0 },
    ]))
    vi.mocked(groupsApi.list).mockResolvedValue(page([{ id: 3, name: 'Python PRO — группа 3' }]) as never)
    vi.mocked(examsApi.create).mockResolvedValue(buildExamSession({ id: 'new-session' }))
    vi.mocked(groupsApi.get).mockResolvedValue(
      buildGroup({
        id: 3,
        teachers: [buildGroupTeacherSummary({ subject_detail: buildSubject({ name: 'Python' }) })],
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(
      <Routes>
        <Route path="/app/exams" element={<ExamsListPage />} />
        <Route path="/app/exams/:id" element={<div>Session page</div>} />
      </Routes>,
      { route: '/app/exams' },
    )

    await user.click(await screen.findByRole('button', { name: 'Создать сессию' }))
    await screen.findByRole('option', { name: /Python Basics #4/ })
    await user.selectOptions(screen.getByLabelText('Тест *'), 'test-4')
    expect(screen.getByTestId('session-subject')).toHaveTextContent('Python')
    await screen.findByRole('option', { name: 'Python PRO — группа 3' })
    await user.selectOptions(screen.getByLabelText('Группа *'), '3')
    // The group's trainer comes from the Group → Trainer link — not chosen again.
    await waitFor(() => expect(screen.getByTestId('session-trainer')).toHaveTextContent('Айгуль Сатыбалдиева'))
    const date = screen.getByLabelText('Дата *')
    await user.clear(date)
    await user.type(date, '2026-10-04')
    await user.type(screen.getByLabelText('Время начала *'), '14:00')
    await user.type(screen.getByLabelText('Время окончания'), '15:00')
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Создать сессию' }))

    await waitFor(() =>
      expect(examsApi.create).toHaveBeenCalledWith({
        test: 'test-4', group: 3, date: '2026-10-04', start_time: '14:00', end_time: '15:00',
      }),
    )
    expect(await screen.findByText('Session page')).toBeInTheDocument()
  })

  it('requires a test and a group', async () => {
    vi.mocked(examsApi.list).mockResolvedValue(page([]))
    vi.mocked(examsApi.tests).mockResolvedValue(page([]))
    vi.mocked(groupsApi.list).mockResolvedValue(page([]) as never)
    const user = userEvent.setup()
    renderWithProviders(<ExamsListPage />, { route: '/app/exams' })
    await user.click(await screen.findByRole('button', { name: 'Создать сессию' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Создать сессию' }))
    expect(screen.getByText('Выберите тест.')).toBeInTheDocument()
    expect(screen.getByText('Выберите группу.')).toBeInTheDocument()
    expect(examsApi.create).not.toHaveBeenCalled()
  })

  it('starts a session it created', async () => {
    vi.mocked(examsApi.participants).mockResolvedValue({
      session: buildExamSession({ phase: 'scheduled', is_live: false, can_start: true, can_take: true }),
      server_time: '2026-10-02T08:40:00Z',
      participants: [],
    })
    vi.mocked(examsApi.start).mockResolvedValue(buildExamSession())
    const user = userEvent.setup()
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Запустить' }))
    await waitFor(() => expect(examsApi.start).toHaveBeenCalledWith('session-1'))
    // Not live yet → nothing to take.
    expect(screen.queryByRole('button', { name: 'Пройти тест' })).not.toBeInTheDocument()
  })

  it('opens the test on the student test page — its own attempt', async () => {
    const open = vi.spyOn(testPage, 'open').mockImplementation(() => {})
    vi.mocked(examsApi.participants).mockResolvedValue({
      session: buildExamSession({ can_take: true }),
      server_time: '2026-10-02T08:40:00Z',
      participants: [],
    })
    vi.mocked(examsApi.take).mockResolvedValue(
      myAttempt({ status: 'active', score: null, take_url: 'https://api.example/exam/a/attempt-1/?t=signed', result_url: null }),
    )
    const user = userEvent.setup()
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Пройти тест' }))
    await waitFor(() => expect(examsApi.take).toHaveBeenCalledWith('session-1'))
    expect(open).toHaveBeenCalledWith('https://api.example/exam/a/attempt-1/?t=signed')
    open.mockRestore()
  })

  it('shows its own result, separately from the group results', async () => {
    vi.mocked(examsApi.myAttempts).mockResolvedValue([myAttempt()])
    vi.mocked(examsApi.participants).mockResolvedValue({
      session: buildExamSession({ can_take: true }),
      server_time: '2026-10-02T08:40:00Z',
      participants: [
        buildExamParticipant({ id: 'p2', student: { id: 2, name: 'Алиев А.' }, status: 'completed', status_label: 'Завершил', score: 90, result_available: true }),
        buildExamParticipant({ id: 'p3', student: { id: 3, name: 'Садыкова А.' }, status: 'not_started', status_label: 'Не начал', score: null }),
      ],
    })
    renderDetail()

    const mine = await screen.findByRole('region', { name: 'Мой результат' })
    expect(within(mine).getByText('Python Basics #4')).toBeInTheDocument()
    expect(within(mine).getByTestId('my-score')).toHaveTextContent('18 / 20 — 90% · верно 18, ошибок 2')
    expect(within(mine).getByText('Завершён')).toBeInTheDocument()
    expect(examsApi.myAttempts).toHaveBeenCalledWith('session-1')

    expect(screen.getByRole('heading', { name: 'Результаты группы · Python-01' })).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(within(table).getByText('Алиев А.').closest('tr') as HTMLElement).getByRole('button', { name: '90%' })).toBeInTheDocument()
    expect(within(within(table).getByText('Садыкова А.').closest('tr') as HTMLElement).getByText('—')).toBeInTheDocument()
  })

  it('a Trainer sees none of it', async () => {
    mockRole.role = 'teacher'
    vi.mocked(examsApi.list).mockResolvedValue(page([buildExamSession()]))
    renderWithProviders(<ExamsListPage />, { route: '/app/exams' })
    expect(await screen.findByRole('heading', { name: 'Экзамены' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Создать сессию' })).not.toBeInTheDocument()
    expect(examsApi.myAttempts).not.toHaveBeenCalled()
  })
})
