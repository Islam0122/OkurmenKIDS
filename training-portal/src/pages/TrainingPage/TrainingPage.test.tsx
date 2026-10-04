import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, vi } from 'vitest'

import { AppRoutes } from '@/App'
import { routeFetch } from '@/test/testBackend'

afterEach(() => vi.restoreAllMocks())

const PORTAL = {
  hero_title: 'Экзаменге даярдан', hero_subtitle: 'Билимиңди текшер.', start_button_label: 'Тренировка баштоо',
  exam_button_label: 'Экзаменге өтүү', exam_url: 'https://lms.example.com/student/exams/', exam_open_in_new_tab: false,
}
const TEST = {
  id: 't1', title: 'Python Training', description: '', subject: 'Python', level: 'medium', level_display: 'Средний',
  image_url: null, duration: 30, questions_count: 2, max_attempts: null, passing_score: 50,
  show_explanation: true, show_result: true, published: true,
}
const QUESTIONS = [
  { id: 'q1', type: 'single_choice', text: 'Backend?', image_url: null, hint: '', language: null, starter_code: '', points: 1,
    is_required: true, options: [{ id: 'o1', text: 'Python', image_url: null }, { id: 'o2', text: 'HTML', image_url: null }],
    answer: null, checked: false, feedback: null },
  { id: 'q2', type: 'text', text: 'Method?', image_url: null, hint: '', language: null, starter_code: '', points: 1,
    is_required: true, options: [], answer: null, checked: false, feedback: null },
]
const SUMMARY = { attempt_id: 'a1', test_id: 't1', test_title: 'Python Training', student_name: 'Islam', started_at: '2026-10-04T10:00:00Z', expires_at: '2026-10-04T10:30:00Z' }

function backend() {
  return routeFetch({
    'GET /portal/': () => ({ body: PORTAL }),
    'GET /tests/': () => ({ body: [TEST] }),
    'GET /tests/t1/': () => ({ body: TEST }),
    'GET /leaderboard/': () => ({ body: [{ rank: 1, student_name: 'Islam', score: 50, duration_seconds: 60, finished_at: '2026-10-04T10:01:00Z', test_id: 't1', test_title: 'Python Training' }] }),
    'GET /videos/': () => ({ body: [] }),
    'GET /links/': () => ({ body: [] }),
    'POST /attempts/': ({ body }) => (body as { student_name: string }).student_name.length < 2
      ? { status: 400, body: { detail: 'Аты кеминде 2 белгиден турушу керек.', code: 'name_too_short' } }
      : { status: 201, body: { ...SUMMARY, token: 'signed-token' } },
    'GET /attempts/a1/': () => ({ body: { ...SUMMARY, status: 'active', remaining_seconds: 1800, show_explanation: true, questions: QUESTIONS } }),
    'PUT /attempts/a1/answers/q1/': () => ({ body: { saved: true, remaining_seconds: 1790 } }),
    'POST /attempts/a1/answers/q1/check/': () => ({ body: { status: 'incorrect', correct_option_ids: ['o1'], correct_answers: [], code_examples: [], explanation: 'Python — backend тил.' } }),
    'POST /attempts/a1/submit/': () => ({ body: { ...SUMMARY, status: 'completed', finish_reason: 'submitted', finished_at: '2026-10-04T10:05:00Z', duration_seconds: 300, show_result: true, passing_score: 50, score: 0, max_score: 2, percentage: 0, total: 2, correct: 0, incorrect: 1, skipped: 1, pending: 0, passed: false, review: [] } }),
    'GET /attempts/a1/result/': () => ({ body: { ...SUMMARY, status: 'completed', finish_reason: 'submitted', finished_at: '2026-10-04T10:05:00Z', duration_seconds: 300, show_result: true, passing_score: 50, score: 0, max_score: 2, percentage: 0, total: 2, correct: 0, incorrect: 1, skipped: 1, pending: 0, passed: false, review: [] } }),
  })
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>)
}

describe('training flow (through the API layer)', () => {
  it('starts with a name, saves answers on the backend, shows its feedback, submits and shows its result', async () => {
    const user = userEvent.setup()
    const { calls } = backend()
    renderAt('/training/t1')

    const dialog = await screen.findByRole('dialog', { name: 'Атыңызды жазыңыз' })
    await user.type(within(dialog).getByLabelText('Атыңыз'), 'Islam')
    await user.click(within(dialog).getByRole('button', { name: 'Баштоо' }))
    expect((await screen.findAllByText('Суроо 1 / 2')).length).toBeGreaterThan(0)
    expect(calls.find((c) => c.method === 'POST' && c.path === '/attempts/')?.body).toEqual({ test_id: 't1', student_name: 'Islam' })

    await user.click(screen.getByRole('radio', { name: /HTML/ }))
    await user.click(screen.getByRole('button', { name: 'Текшерүү' }))
    expect(await screen.findByText('Туура эмес жооп')).toBeInTheDocument()
    expect(screen.getByText('Python — backend тил.')).toBeInTheDocument()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.body).toEqual({ options: ['o2'], text: '' })
    expect(put?.headers['X-Attempt-Token']).toBe('signed-token')
    expect(screen.getByRole('radio', { name: /HTML/ })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Кийинки' }))
    await user.click(screen.getByRole('button', { name: 'Аяктоо' }))
    const confirm = await screen.findByRole('dialog', { name: 'Тренировканы аяктайсызбы?' })
    await user.click(within(confirm).getByRole('button', { name: 'Аяктоо' }))

    expect(await screen.findByText('Көбүрөөк машыгуу керек')).toBeInTheDocument()
    expect(screen.getByText('0 / 2')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.path === '/attempts/a1/submit/')).toBe(true)
    expect(window.localStorage.getItem('okurmen_active_attempts')).toBe('{}')
  })

  it('shows the backend’s reason when it rejects the name', async () => {
    const user = userEvent.setup()
    backend()
    renderAt('/training/t1')
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Атыңыз'), 'I')
    await user.click(within(dialog).getByRole('button', { name: 'Баштоо' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('кеминде 2')
  })

  it('resumes the attempt after a reload', async () => {
    window.localStorage.setItem('okurmen_active_attempts', JSON.stringify({ t1: { attemptId: 'a1', token: 'signed-token' } }))
    backend()
    renderAt('/training/t1')
    expect(await screen.findByText(/Мурунку тренировкаңды улантып жатасың/)).toBeInTheDocument()
  })
})

describe('content comes from the backend', () => {
  it('home: hero texts, tests, leaderboard and the exam URL from the API', async () => {
    backend()
    renderAt('/')
    expect(await screen.findByText('даярдан')).toBeInTheDocument()
    expect(screen.getByText('Билимиңди текшер.')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Python Training' })).toBeInTheDocument()
    const examLinks = await screen.findAllByRole('link', { name: /Экзаменге өтүү/ })
    expect(examLinks[0]).toHaveAttribute('href', 'https://lms.example.com/student/exams/')
    expect((await screen.findAllByText('Islam')).length).toBeGreaterThan(0)
  })

  it('no exam URL in the backend → no exam button', async () => {
    routeFetch({
      'GET /portal/': () => ({ body: { ...PORTAL, exam_url: '' } }),
      'GET /tests/': () => ({ body: [] }),
      'GET /leaderboard/': () => ({ body: [] }),
      'GET /videos/': () => ({ body: [] }),
      'GET /links/': () => ({ body: [] }),
    })
    renderAt('/')
    expect(await screen.findByText('Азырынча жарыяланган тренировкалык тесттер жок.')).toBeInTheDocument()
    await act(async () => {})
    expect(screen.queryByRole('link', { name: /Экзаменге өтүү/ })).not.toBeInTheDocument()
  })

  it('shows an error with retry when the backend is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    renderAt('/videos')
    expect(await screen.findByText(/Сервер менен байланыш жок/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Кайра аракет кылуу' })).toBeInTheDocument()
  })
})
