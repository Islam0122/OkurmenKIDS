import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { homeFor } from '@/lib/roles'
import { renderWithProviders } from '@/test/testUtils'
import type { PortalDashboard, PortalHomeworkDetail, PortalMe, PortalStudent } from '@/types/studentPortal'

vi.mock('@/api/studentPortal', () => ({
  studentPortalApi: {
    me: vi.fn(),
    changePassword: vi.fn(),
    dashboard: vi.fn(),
    homeworkDetail: vi.fn(),
  },
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 9, role: 'student_parent', username: 'aibek.asanov' }, logout: vi.fn() }),
}))

import { studentPortalApi } from '@/api/studentPortal'

import { CredentialsCard } from '@/features/assistant/actions/StudentAccount'
import { StudentPortalLayout } from './StudentPortalLayout'
import { StudentDashboardPage } from './pages/DashboardPage'
import { StudentHomeworkDetailPage } from './pages/HomeworkPages'
import { translate, DICTIONARIES } from './i18n'

function child(id: number, first: string): PortalStudent {
  return {
    id, first_name: first, last_name: 'Асанов', full_name: `${first} Асанов`, photo: null, birth_date: null, status: 'active',
    group: { id: 1, name: `PRO-0${id}` }, course: { id: 1, name: 'Python' }, branch: null, enrollment_date: '2026-09-01',
  }
}

const ME: PortalMe = { login: 'aibek.asanov', must_change_password: false, can_view_payments: true, students: [child(1, 'Айбек'), child(2, 'Айжан')] }

function dashboard(student: PortalStudent): PortalDashboard {
  const empty = { marked: 0, present: 0, late: 0, absent: 0, excused: 0, attended: 0, percent: null }
  return {
    student, today: '2026-11-14', today_lessons: [], upcoming_lessons: [],
    homework: { open: [], open_count: 0, not_submitted_count: 0, next_deadline: null },
    attendance: { month: empty, overall: empty },
    performance: { average_score: null, month_average_score: null, homework_rate: null, scored_count: 0 },
    xp: { month: { attendance: 0, homework: 0, tests: 0, total: 0 }, total: 120, level: { level: 2, floor: 100, next: 300, progress: 10 } },
    achievements: [], feedback: [],
    notifications: [{ id: 'n1', kind: 'homework_due', date: '2026-11-15', priority: 2, params: { homework_id: 5, title: 'Цикл for', days_left: 1 } }],
    payments: null,
  }
}

function renderPortal() {
  return renderWithProviders(
    <Routes>
      <Route path="/student" element={<StudentPortalLayout />}>
        <Route index element={<StudentDashboardPage />} />
      </Route>
    </Routes>,
    { route: '/student' },
  )
}

describe('Student & Parent Portal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.dashboard).mockImplementation(async (id) => dashboard(ME.students.find((s) => s.id === id)!))
  })

  it('lands a portal account on /student and nowhere else', () => {
    expect(homeFor('student_parent', '/app/dashboard')).toBe('/student')
    expect(homeFor('student_parent', '/student/homework')).toBe('/student/homework')
  })

  it('holds the account on the password change until the temporary password is replaced', async () => {
    vi.mocked(studentPortalApi.me).mockResolvedValueOnce({ ...ME, must_change_password: true }).mockResolvedValue(ME)
    vi.mocked(studentPortalApi.changePassword).mockResolvedValue({ must_change_password: false })
    renderPortal()
    expect(await screen.findByText('Придумайте свой пароль')).toBeInTheDocument()
    expect(studentPortalApi.dashboard).not.toHaveBeenCalled()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Текущий (временный) пароль'), 'Hk7m-pQ3x-9tRw')
    await user.type(screen.getByLabelText('Новый пароль'), 'MyOwn-Secret-2026')
    await user.type(screen.getByLabelText('Повторите новый пароль'), 'MyOwn-Secret-2026')
    await user.click(screen.getByRole('button', { name: 'Сохранить пароль' }))
    await waitFor(() => expect(studentPortalApi.changePassword).toHaveBeenCalledWith({
      current_password: 'Hk7m-pQ3x-9tRw', new_password: 'MyOwn-Secret-2026', new_password_confirm: 'MyOwn-Secret-2026',
    }))
    expect(await screen.findByRole('heading', { name: 'Айбек Асанов' })).toBeInTheDocument()
  })

  it('switches between the children of one family account', async () => {
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    renderPortal()
    expect(await screen.findByRole('heading', { name: 'Айбек Асанов' })).toBeInTheDocument()
    expect(screen.getByText('Скоро срок: «Цикл for»')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getAllByRole('button', { name: /Ребёнок: Айбек Асанов/ })[0])
    await user.click(screen.getByRole('option', { name: /Айжан Асанов/ }))
    expect(await screen.findByRole('heading', { name: 'Айжан Асанов' })).toBeInTheDocument()
    expect(studentPortalApi.dashboard).toHaveBeenLastCalledWith(2)
  })

  it('speaks Kyrgyz when asked', async () => {
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    renderPortal()
    await screen.findByRole('heading', { name: 'Айбек Асанов' })
    await userEvent.setup().click(screen.getAllByRole('button', { name: 'KG' })[0])
    expect(await screen.findByText('Саламатсызбы!')).toBeInTheDocument()
    expect(screen.getByText('Мөөнөтү жакындады: «Цикл for»')).toBeInTheDocument()
  })

  it('has every Russian key translated to Kyrgyz', () => {
    expect(Object.keys(DICTIONARIES.ky).sort()).toEqual(Object.keys(DICTIONARIES.ru).sort())
    expect(translate('ru', 'dash.level', { n: 3 })).toBe('Уровень 3')
  })
})

describe('One-time credentials card', () => {
  it('shows the login and password with copy buttons', async () => {
    renderWithProviders(<CredentialsCard credentials={{ login: 'aibek.asanov', password: 'Hk7m-pQ3x-9tRw' }} studentName="Айбек Асанов" />)
    expect(screen.getByText('aibek.asanov')).toBeInTheDocument()
    expect(screen.getByText('Hk7m-pQ3x-9tRw')).toBeInTheDocument()
    const user = userEvent.setup() // installs a clipboard stub
    await user.click(screen.getByRole('button', { name: 'Копировать всё' }))
    expect(await screen.findByRole('button', { name: 'Скопировано' })).toBeInTheDocument()
    const copied = await navigator.clipboard.readText()
    expect(copied).toContain('Логин: aibek.asanov')
    expect(copied).toContain('Временный пароль: Hk7m-pQ3x-9tRw')
    expect(screen.getAllByRole('button', { name: 'Копировать' })).toHaveLength(2)
  })
})

function homework(overrides: Partial<PortalHomeworkDetail> = {}): PortalHomeworkDetail {
  return {
    id: 5, title: 'Цикл for', assigned_date: '2026-11-12', deadline: '2026-11-16', days_left: 2, state: 'awaiting', is_open: true,
    lesson: { id: 3, date: '2026-11-12', topic: 'Циклы', lesson_number: 7, description: '' },
    subject: { id: 1, name: 'Python' }, teacher: { id: 1, name: 'Ислам' }, score: null, has_feedback: false,
    evaluated_at: null, checked_at: null, created_at: '2026-11-12T10:00:00Z',
    description: 'Решите 5 задач на цикл for.', attachments: [], feedback: '', ...overrides,
  }
}

describe('Homework page (offline checking, read-only)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
  })

  function renderDetail() {
    return renderWithProviders(
      <Routes>
        <Route path="/student" element={<StudentPortalLayout />}>
          <Route path="homework/:id" element={<StudentHomeworkDetailPage />} />
        </Route>
      </Routes>,
      { route: '/student/homework/5' },
    )
  }

  it('has no way to submit work and shows no grade before the trainer evaluates', async () => {
    vi.mocked(studentPortalApi.homeworkDetail).mockResolvedValue(homework())
    renderDetail()
    expect(await screen.findByRole('heading', { name: 'Цикл for' })).toBeInTheDocument()
    expect(screen.getByText('Решите 5 задач на цикл for.')).toBeInTheDocument()
    expect(screen.getByText('Ожидает проверки')).toBeInTheDocument()
    expect(screen.getByTestId('hw-grade')).toHaveTextContent('Ещё не оценено')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Сдать|Отправить/ })).not.toBeInTheDocument()
    expect(document.querySelector('form')).toBeNull()
    expect(studentPortalApi).not.toHaveProperty('submitHomework')
  })

  it('shows the status, grade and comment the trainer saved', async () => {
    vi.mocked(studentPortalApi.homeworkDetail).mockResolvedValue(
      homework({ state: 'checked', is_open: false, score: 10, feedback: 'Отлично!', evaluated_at: '2026-11-14T09:00:00Z' }),
    )
    renderDetail()
    expect(await screen.findByText('Проверено')).toBeInTheDocument()
    expect(screen.getByTestId('hw-grade')).toHaveTextContent('10 / 10')
    expect(screen.getByTestId('hw-feedback')).toHaveTextContent('«Отлично!»')
    expect(screen.getByText('Проверено тренером: 14.11.2026')).toBeInTheDocument()
  })

  it.each([
    ['not_submitted', 'Не сдано'],
    ['submitted', 'Сдано'],
    ['late', 'Сдано с опозданием'],
  ] as const)('shows the trainer status %s', async (state, label) => {
    vi.mocked(studentPortalApi.homeworkDetail).mockResolvedValue(homework({ state, is_open: state === 'not_submitted' }))
    renderDetail()
    expect(await screen.findByText(label)).toBeInTheDocument()
  })
})
