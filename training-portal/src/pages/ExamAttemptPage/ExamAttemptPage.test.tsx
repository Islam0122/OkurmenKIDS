import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'

import { AppRoutes } from '@/App'
import { routeFetch } from '@/test/testBackend'

afterEach(() => vi.restoreAllMocks())
beforeEach(() => window.sessionStorage.clear())

const QUESTIONS = [
  { id: 'q1', type: 'single_choice', text: 'Backend?', image_url: null, hint: '', language: null, starter_code: '', points: 1,
    is_required: true, options: [{ id: 'o1', text: 'Python', image_url: null }, { id: 'o2', text: 'HTML', image_url: null }],
    answer: null, checked: false, feedback: null },
  { id: 'q2', type: 'single_choice', text: 'Frontend?', image_url: null, hint: '', language: null, starter_code: '', points: 1,
    is_required: false, options: [{ id: 'o3', text: 'CSS', image_url: null }, { id: 'o4', text: 'SQL', image_url: null }],
    answer: null, checked: false, feedback: null },
]
const STATE = {
  attempt_id: 'e1', test_id: 's1', test_title: 'IT — Month 1', student_name: 'Айбек Асанов', started_at: '2026-10-05T09:00:00Z',
  expires_at: '2026-10-05T09:45:00Z', status: 'active', remaining_seconds: 2538, show_explanation: false, mode: 'exam', paused: false,
  subject: 'IT',
  security: { require_fullscreen: false, track_tab_switches: true, max_tab_switches: 3, block_copy_paste: true },
  tab_switch_count: 0, violation_count: 0, questions: QUESTIONS,
}
const RESULT = {
  ...STATE, status: 'completed', finish_reason: 'submitted', finished_at: '2026-10-05T09:38:42Z', duration_seconds: 2322,
  show_result: true, passing_score: 60, score: 1, max_score: 2, percentage: 50, total: 2, correct: 1, incorrect: 0, skipped: 1,
  pending: 0, passed: false, review: [],
}

function backend(stateOverride = {}) {
  return routeFetch({
    'GET /exam-attempts/e1/': ({ headers }) => headers['X-Attempt-Token'] === 'tok'
      ? { body: { ...STATE, ...stateOverride } } : { status: 403, body: { detail: 'no', code: 'forbidden' } },
    'PUT /exam-attempts/e1/answers/q1/': () => ({ body: { saved: true, remaining_seconds: 2500 } }),
    'PUT /exam-attempts/e1/answers/q2/': () => ({ body: { saved: true, remaining_seconds: 2500 } }),
    'PATCH /exam-attempts/e1/': () => ({ body: { saved: true, remaining_seconds: 2500 } }),
    'POST /exam-attempts/e1/submit/': () => ({ body: RESULT }),
    'GET /exam-attempts/e1/result/': () => ({ body: RESULT }),
    'POST /exam-attempts/e1/events/': () => ({ body: { tab_switch_count: 1, violation_count: 1, max_tab_switches: 3 } }),
  })
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>)
}

describe('exam on the shared test screen', () => {
  it('opens from the exam link, autosaves, asks before finishing and shows the exam result', async () => {
    const { calls } = backend()
    window.history.replaceState(null, '', '/exam/e1#t=tok')
    const user = userEvent.setup()
    renderAt('/exam/e1')

    expect(await screen.findByText('Экзамен')).toBeInTheDocument()  // exam badge, same bar as training
    expect(screen.getByText('IT — Month 1')).toBeInTheDocument()
    expect(screen.getAllByText('Суроо 1 / 2').length).toBeGreaterThan(0)
    expect(screen.getByText('Жооп берилди: 0 · Калды: 2')).toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent('42:18')
    expect(screen.queryByRole('button', { name: 'Текшерүү' })).not.toBeInTheDocument()  // no answer checking in an exam
    expect(screen.queryByRole('button', { name: 'Артка' })).not.toBeInTheDocument()     // no leaving to the site
    expect(window.location.hash).toBe('')                                                // token taken out of the address bar
    expect(window.sessionStorage.getItem('okurmen_exam_e1')).toBe('tok')

    await user.click(screen.getByText('Python'))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.path === '/exam-attempts/e1/answers/q1/')).toBe(true))
    expect(await screen.findByText('Жооп берилди: 1 · Калды: 1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Экзаменди аяктоо/ }))
    const dialog = screen.getByRole('dialog', { name: 'Экзаменди аяктайсызбы?' })
    expect(within(dialog).getByText('Аяктагандан кийин жоопторду өзгөртүү мүмкүн эмес.')).toBeInTheDocument()
    expect(within(dialog).getByText('Жооп берилбеген суроолор: 1')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Экзаменди аяктоо' }))

    expect(await screen.findByText('Экзамен аяктады')).toBeInTheDocument()
    expect(document.querySelector('.result-card')).not.toBeNull()  // the training result card
    // The result is the last screen: no way back to a cabinet, no retake.
    expect(screen.getByText('Экзамен аяктады. Бул баракты жаап койсоңуз болот.')).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
    expect(document.body.textContent).not.toMatch(/кабинет/i)
    expect(screen.queryByRole('button', { name: 'Кайра тапшыруу' })).not.toBeInTheDocument()
  })

  it('a reload restores the same attempt with its saved answers', async () => {
    backend({ questions: [{ ...QUESTIONS[0], answer: { options: ['o1'], text: '' } }, QUESTIONS[1]] })
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    renderAt('/exam/e1')
    expect(await screen.findByText(/Экзамен калыбына келтирилди/)).toBeInTheDocument()
    expect(screen.getAllByText('Суроо 2 / 2').length).toBeGreaterThan(0)  // first unanswered question
    expect(screen.getByText('Жооп берилди: 1 · Калды: 1')).toBeInTheDocument()
  })

  it('a reload opens the question the student was on (server position), not the first unanswered', async () => {
    backend({ current_question_id: 'q2' })
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    renderAt('/exam/e1')
    expect((await screen.findAllByText('Суроо 2 / 2')).length).toBeGreaterThan(0)
    expect(screen.getByText(/Экзамен калыбына келтирилди/)).toBeInTheDocument()
  })

  it('a fresh exam on question 1 is not announced as restored', async () => {
    backend({ current_question_id: 'q1' })
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    renderAt('/exam/e1')
    expect((await screen.findAllByText('Суроо 1 / 2')).length).toBeGreaterThan(0)
    expect(screen.queryByText(/калыбына келтирилди/)).not.toBeInTheDocument()
  })

  it('a saved position that no longer exists falls back to the first unanswered question', async () => {
    backend({ current_question_id: 'gone', questions: [{ ...QUESTIONS[0], answer: { options: ['o1'], text: '' } }, QUESTIONS[1]] })
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    renderAt('/exam/e1')
    expect((await screen.findAllByText('Суроо 2 / 2')).length).toBeGreaterThan(0)
  })

  it('moving between questions saves the position once (debounced, ordered by seq)', async () => {
    const { calls } = backend()
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    const user = userEvent.setup()
    renderAt('/exam/e1')
    await screen.findByText('Экзамен')
    await user.click(screen.getByRole('button', { name: 'Кийинки' }))
    await user.click(screen.getByRole('button', { name: /Мурунку/ }))
    await user.click(screen.getByRole('button', { name: 'Кийинки' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH').length).toBe(1))
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(patch.body).toMatchObject({ current_question_id: 'q2' })
    expect(typeof (patch.body as { seq: number }).seq).toBe('number')
    expect(patch.headers['X-Attempt-Token']).toBe('tok')
    await waitFor(() => expect(window.sessionStorage.getItem('okurmen_pending_e1')).toBeNull())
  })

  it('every autosave carries a growing seq', async () => {
    const { calls } = backend()
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    const user = userEvent.setup()
    renderAt('/exam/e1')
    await user.click(await screen.findByText('Python'))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').length).toBe(1))
    await user.click(screen.getByText('HTML'))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT').length).toBe(2))
    const [first, second] = calls.filter((c) => c.method === 'PUT').map((c) => c.body as { seq: number; options: string[] })
    expect(first.options).toEqual(['o1'])
    expect(second.options).toEqual(['o2'])
    expect(second.seq).toBeGreaterThan(first.seq)
  })

  it('an answer not yet saved when the page reloaded is shown and sent again', async () => {
    const { calls } = backend()
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    window.sessionStorage.setItem('okurmen_pending_e1', JSON.stringify({
      answers: { q2: { value: { options: ['o3'], text: '' }, seq: 1234 } },
      position: { questionId: 'q2', seq: 1235 },
    }))
    renderAt('/exam/e1')
    expect((await screen.findAllByText('Суроо 2 / 2')).length).toBeGreaterThan(0)
    expect(screen.getByRole('radio', { name: /CSS/ })).toBeChecked()
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ options: ['o3'], text: '', seq: 1234 }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ current_question_id: 'q2', seq: 1235 }))
    await waitFor(() => expect(window.sessionStorage.getItem('okurmen_pending_e1')).toBeNull())
  })

  it('shows no training wording inside the exam', async () => {
    backend()
    window.sessionStorage.setItem('okurmen_exam_e1', 'tok')
    const user = userEvent.setup()
    renderAt('/exam/e1')
    await screen.findByText('Экзамен')
    await user.click(screen.getByRole('button', { name: /Экзаменди аяктоо/ }))
    expect(document.body.textContent).not.toMatch(/тренировк|Текшерүү|Башынан баштоо/i)
  })

  it('without the token from the exam link there is no exam', async () => {
    backend()
    renderAt('/exam/e1')
    expect(await screen.findByText(/шилтеме жараксыз/)).toBeInTheDocument()
  })
})
