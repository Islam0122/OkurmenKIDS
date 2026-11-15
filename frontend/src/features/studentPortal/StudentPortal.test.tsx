import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { homeFor } from '@/lib/roles'
import { renderWithProviders } from '@/test/testUtils'
import type { PortalDashboard, PortalHomeworkDetail, PortalLesson, PortalMe, PortalStudent } from '@/types/studentPortal'

vi.mock('@/api/studentPortal', () => ({
  studentPortalApi: {
    me: vi.fn(),
    changePassword: vi.fn(),
    dashboard: vi.fn(),
    homeworkDetail: vi.fn(),
    nextHomework: vi.fn(),
    homework: vi.fn(),
    achievements: vi.fn(),
    payments: vi.fn(),
    transactions: vi.fn(),
    paymentDocuments: vi.fn(),
    receipt: vi.fn(),
    receiptPdf: vi.fn(),
    attendance: vi.fn(),
    attendanceOverview: vi.fn(),
    attendanceHistory: vi.fn(),
  },
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 9, role: 'student_parent', username: 'aibek.asanov' }, logout: vi.fn() }),
}))

import { studentPortalApi } from '@/api/studentPortal'

import { CredentialsCard } from '@/features/assistant/actions/StudentAccount'
import { StudentPortalLayout } from './StudentPortalLayout'
import { StudentDashboardPage } from './pages/DashboardPage'
import { StudentHomeworkDetailPage, StudentHomeworkPage } from './pages/HomeworkPages'
import { StudentAchievementsPage } from './pages/AchievementsPage'
import { StudentPaymentsPage } from './pages/PaymentsPage'
import { StudentAttendancePage } from './pages/AttendancePage'
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
    student, today: '2026-11-14', course_progress: null, today_lessons: [], upcoming_lessons: [],
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
    expect(await screen.findByRole('heading', { name: 'Привет, Айбек!' })).toBeInTheDocument()
  })

  it('switches between the children of one family account', async () => {
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    renderPortal()
    expect(await screen.findByRole('heading', { name: 'Привет, Айбек!' })).toBeInTheDocument()
    expect(screen.getByText('Скоро срок: «Цикл for»')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getAllByRole('button', { name: /Ребёнок: Айбек Асанов/ })[0])
    await user.click(screen.getByRole('option', { name: /Айжан Асанов/ }))
    expect(await screen.findByRole('heading', { name: 'Привет, Айжан!' })).toBeInTheDocument()
    expect(studentPortalApi.dashboard).toHaveBeenLastCalledWith(2)
  })

  it('speaks Kyrgyz when asked', async () => {
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    renderPortal()
    await screen.findByRole('heading', { name: 'Привет, Айбек!' })
    await userEvent.setup().click(screen.getAllByRole('button', { name: 'KG' })[0])
    expect(await screen.findByText('Салам, Айбек!')).toBeInTheDocument()
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
    subject: { id: 1, name: 'Python' }, group: { id: 1, name: 'PRO-01' }, teacher: { id: 1, name: 'Ислам' }, score: null, has_feedback: false,
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
    expect(screen.getByTestId('hw-grade')).toHaveTextContent('10/10')
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

function lesson18(): PortalLesson {
  return {
    id: 18, date: '2026-11-17', start: '16:00', end: '17:30', subject: { id: 1, name: 'Python' }, teacher: null,
    group: { id: 1, name: 'PRO-01' }, course: null, room: null, branch: null, topic: 'Функции', lesson_number: 18,
    status: 'scheduled', cancellation_reason: '', attendance: null,
  }
}

describe('Homework list: only the next lesson', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
  })

  function renderList(route = '/student/homework') {
    return renderWithProviders(
      <Routes>
        <Route path="/student" element={<StudentPortalLayout />}>
          <Route path="homework" element={<StudentHomeworkPage />} />
        </Route>
      </Routes>,
      { route },
    )
  }

  it('shows the homework of the next lesson in full, and nothing else', async () => {
    vi.mocked(studentPortalApi.nextHomework).mockResolvedValue({
      has_group: true,
      lessons: [{ lesson: lesson18(), homework: [homework({ id: 81, title: 'ДЗ к уроку 18', lesson: { ...homework().lesson, lesson_number: 18 } })] }],
    })
    renderList()
    expect((await screen.findAllByText('Урок 18')).length).toBeGreaterThan(0)
    expect(screen.getByText('PRO-01')).toBeInTheDocument()
    expect(screen.getByText('ДЗ к уроку 18')).toBeInTheDocument()
    expect(screen.getByText('Решите 5 задач на цикл for.')).toBeInTheDocument()
    expect(screen.getByText(/Ещё не оценено/)).toBeInTheDocument()
    expect(studentPortalApi.homework).not.toHaveBeenCalled()
  })

  it('says when the next lesson has no homework yet', async () => {
    vi.mocked(studentPortalApi.nextHomework).mockResolvedValue({ has_group: true, lessons: [{ lesson: lesson18(), homework: [] }] })
    renderList()
    expect(await screen.findByText('Пока домашнего задания нет')).toBeInTheDocument()
  })

  it('shows an empty state when no next lesson is scheduled', async () => {
    vi.mocked(studentPortalApi.nextHomework).mockResolvedValue({ has_group: true, lessons: [] })
    renderList()
    expect(await screen.findByText('Следующее занятие пока не запланировано.')).toBeInTheDocument()
  })

  it('keeps earlier homework under «История»', async () => {
    vi.mocked(studentPortalApi.nextHomework).mockResolvedValue({ has_group: true, lessons: [] })
    vi.mocked(studentPortalApi.homework).mockResolvedValue({
      count: 1, next: null, previous: null,
      results: [{ ...homework({ id: 16, title: 'ДЗ к уроку 16', state: 'checked', score: 9 }) }],
    })
    renderList()
    await userEvent.setup().click(await screen.findByRole('tab', { name: 'История' }))
    expect(await screen.findByText('ДЗ к уроку 16')).toBeInTheDocument()
    expect(screen.getByText('9/10')).toBeInTheDocument()
    expect(studentPortalApi.homework).toHaveBeenCalledWith(1, 'all', 1)
  })
})

function gamificationPayload() {
  const days = Array.from({ length: 7 }, (_, i) => ({
    date: `2026-11-${String(8 + i).padStart(2, '0')}`, xp: i === 5 ? 39 : 0, xp_attendance: i === 5 ? 10 : 0,
    xp_homework: i === 5 ? 29 : 0, xp_tests: 0, lessons: i === 5 ? 1 : 0, homework: i === 5 ? 1 : 0, tests: 0,
  }))
  return {
    level: { level: 5, floor: 1000, next: 1500, progress: 13, total_xp: 1065, to_next: 435, reached_on: '2026-11-01' },
    xp: { total: { attendance: 300, homework: 700, tests: 65, total: 1065 }, month: { attendance: 15, homework: 53, tests: 0, total: 68 }, projects_supported: false },
    achievements: [
      { id: 'homework_done-20', code: 'homework_done' as const, category: 'homework' as const, rarity: 'rare' as const, threshold: 20, current: 20, unlocked: true, unlocked_on: '2026-10-02', xp_reward: null },
      { id: 'homework_done-50', code: 'homework_done' as const, category: 'homework' as const, rarity: 'legendary' as const, threshold: 50, current: 42, unlocked: false, unlocked_on: null, xp_reward: null },
    ],
    categories: ['homework', 'quality', 'attendance', 'level', 'scholarship'] as ('homework' | 'quality' | 'attendance' | 'level' | 'scholarship')[],
    goals: [
      { code: 'homework_done' as const, category: 'homework' as const, rarity: 'legendary' as const, current: 42, target: 50, remaining: 8, xp_reward: null },
      { code: 'level' as const, category: 'level' as const, rarity: null, current: 1065, target: 1500, remaining: 435, xp_reward: null, params: { level: 6 } },
    ],
    weekly: { start: '2026-11-08', end: '2026-11-14', days, total: 39, previous_total: 10 },
    timeline: [{ kind: 'level' as const, date: '2026-11-01', level: 5 }],
  }
}

function renderAchievements() {
  return renderWithProviders(
    <Routes><Route path="/student" element={<StudentPortalLayout />}><Route path="achievements" element={<StudentAchievementsPage />} /></Route></Routes>,
    { route: '/student/achievements' },
  )
}

describe('Redesigned portal pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
  })

  it('shows the Kyrgyz empty state when the next lesson has no homework', async () => {
    window.localStorage.setItem('okk-student-portal-lang', 'ky')
    vi.mocked(studentPortalApi.nextHomework).mockResolvedValue({ has_group: true, lessons: [{ lesson: lesson18(), homework: [] }] })
    renderWithProviders(
      <Routes><Route path="/student" element={<StudentPortalLayout />}><Route path="homework" element={<StudentHomeworkPage />} /></Route></Routes>,
      { route: '/student/homework' },
    )
    expect(await screen.findByText('Азырынча үй тапшырмасы жок')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('renders the achievements page from real XP, badges and next goals', async () => {
    vi.mocked(studentPortalApi.achievements).mockResolvedValue(gamificationPayload())
    renderAchievements()
    expect(await screen.findByText('1065')).toBeInTheDocument()
    expect(screen.getByText('До уровня 6 осталось 435 XP')).toBeInTheDocument()
    expect(screen.getByText('Мастер заданий · 20')).toBeInTheDocument()
    expect(screen.getByText('Легендарное')).toBeInTheDocument()
    expect(screen.getByText('Получено 1 из 2')).toBeInTheDocument()
    expect(screen.getAllByText('Сдать 50 домашних заданий').length).toBeGreaterThan(1) // locked badge + goal
    expect(screen.getByText(/Осталось 8/)).toBeInTheDocument()
    expect(screen.getByText('+29 XP к прошлой неделе')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Достижения' }).length).toBeGreaterThan(0)
  })

  it('filters the collection by state and category', async () => {
    vi.mocked(studentPortalApi.achievements).mockResolvedValue(gamificationPayload())
    renderAchievements()
    await screen.findByText('Мастер заданий · 20')
    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: 'Ещё впереди' }))
    expect(screen.queryByText('Мастер заданий · 20')).not.toBeInTheDocument()
    expect(screen.getByText('Мастер заданий · 50')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Все' }))
    await user.click(screen.getByRole('button', { name: 'Посещение' }))
    expect(screen.getByText('В этой категории пока ничего нет.')).toBeInTheDocument()
  })

  it('celebrates only a level reached since the last visit, and marks new badges', async () => {
    window.localStorage.setItem('okk-sp-seen-level-1', '4')
    window.localStorage.setItem('okk-sp-seen-badges-1', '[]')
    vi.mocked(studentPortalApi.achievements).mockResolvedValue(gamificationPayload())
    renderAchievements()
    expect(await screen.findByRole('dialog', { name: 'Новый уровень!' })).toBeInTheDocument()
    expect(screen.getByText('Ты достиг уровня 5. Так держать!')).toBeInTheDocument()
    expect(screen.getByText('Новое')).toBeInTheDocument()
  })

  it('never celebrates on the first visit', async () => {
    vi.mocked(studentPortalApi.achievements).mockResolvedValue(gamificationPayload())
    renderAchievements()
    await screen.findByText('1065')
    expect(screen.queryByRole('dialog', { name: 'Новый уровень!' })).not.toBeInTheDocument()
    expect(screen.queryByText('Новое')).not.toBeInTheDocument()
    expect(window.localStorage.getItem('okk-sp-seen-level-1')).toBe('5')
  })
})

describe('Finance page (read-only accounting data)', () => {
  const invoice = {
    id: 4, number: 'INV-2026-000004', kind: 'PACKAGE' as const, month_number: null, package_number: 4, course: 'Python 8 уроков',
    subject: 'Python', issue_date: '2026-08-13', period_date: '2026-08-13', due_date: '2026-08-18', due_lesson: null,
    lessons_used: null, amount: '6000.00', paid: '3500.00', adjusted: '0.00', balance: '2500.00', status: 'OVERDUE',
    stage: 'overdue' as const, overdue_since: '2026-08-19', paid_at: null,
  }
  const receipt = {
    id: 11, number: 'OK-2026-000004', kind: 'PAYMENT' as const, status: 'ISSUED' as const, issued_at: '2026-11-14T10:00:00Z',
    received_date: '2026-11-14', amount: '6000.00', currency: 'KGS', student: 'Асанов Айбек', course: 'Python 8 уроков',
    group: 'PRO-01', method: 'cash' as const, reference: '', cashier: 'Гульнара Бухгалтер', cancelled_at: null,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    vi.mocked(studentPortalApi.payments).mockResolvedValue({
      status: 'overdue', percent_paid: 51, next_payment: invoice, open_invoices: [invoice], contracts: [], currency: 'KGS',
      summary: { contract_price: null, invoiced: '42000.00', paid: '21500.00', discount: '0.00', adjusted: '0.00', debt: '20500.00',
        due_now: '20500.00', overpayment: '0.00', contracts_count: 1, has_debt: true },
    })
    vi.mocked(studentPortalApi.transactions).mockResolvedValue({ results: [
      { id: 1, date: '2026-11-14', kind: 'payment', status: 'completed', amount: '6000.00', currency: 'KGS', course: 'Программирование',
        method: 'cash', reference: '', purpose: 'tuition', service_start: null, service_end: null, cashier: 'Гульнара Бухгалтер',
        receipt: { id: 11, number: 'OK-2026-000004', status: 'ISSUED' } },
      { id: 2, date: '2026-10-01', kind: 'payment', status: 'completed', amount: '700.00', currency: 'KGS', course: null,
        method: 'bank', reference: 'PP-1', purpose: '', service_start: null, service_end: null, cashier: '', receipt: null },
    ] })
    vi.mocked(studentPortalApi.receipt).mockResolvedValue({
      ...receipt, payer: 'Асанова Жылдыз', purpose: 'Оплата обучения', purpose_lines: [], previously_paid: '21500.00',
      outstanding: '14500.00', credit: '0.00', has_balances: true,
    })
    vi.mocked(studentPortalApi.receiptPdf).mockResolvedValue(new Blob(['%PDF-1.4'], { type: 'application/pdf' }))
    vi.mocked(studentPortalApi.paymentDocuments).mockResolvedValue({ receipts: [receipt], invoices: [invoice] })
    // jsdom has no object URLs; browsers do.
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:receipt'), revokeObjectURL: vi.fn() })
  })

  function renderPayments(route = '/student/payments') {
    return renderWithProviders(
      <Routes><Route path="/student" element={<StudentPortalLayout />}><Route path="payments" element={<StudentPaymentsPage />} /></Route></Routes>,
      { route },
    )
  }

  it('shows the real summary, labels a package tariff total as charged, and lists the overdue invoice', async () => {
    renderPayments()
    expect(await screen.findByText('Есть просрочка')).toBeInTheDocument()
    expect(screen.getByText('51%')).toBeInTheDocument()
    expect(screen.getByText('Начислено')).toBeInTheDocument() // no fixed course price on a package tariff
    expect(screen.queryByText('Стоимость курса')).not.toBeInTheDocument()
    expect(screen.getByText('Пакет уроков №4')).toBeInTheDocument()
    expect(screen.getAllByText('Просрочено').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /Оплатить/ })).not.toBeInTheDocument() // no online payment
  })

  it('links a payment to its accounting receipt and never invents one', async () => {
    renderPayments('/student/payments?tab=history')
    expect(await screen.findByRole('button', { name: 'Чек OK-2026-000004' })).toBeInTheDocument()
    expect(screen.getByText('Без чека')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Чек OK-2026-000004' }))
    expect(await screen.findByRole('dialog', { name: 'OK-2026-000004' })).toBeInTheDocument()
    expect(screen.getByText('Асанова Жылдыз')).toBeInTheDocument()
    expect(screen.getByText(/Не является фискальным документом/)).toBeInTheDocument()
    await waitFor(() => expect(studentPortalApi.receiptPdf).toHaveBeenCalledWith(1, 11))
    expect(screen.getByRole('button', { name: 'Скачать PDF' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Печать' })).toBeInTheDocument()
  })

  it('lists receipts and invoices under «Документы и чеки»', async () => {
    renderPayments('/student/payments?tab=docs')
    expect(await screen.findByText('OK-2026-000004')).toBeInTheDocument()
    expect(screen.getByText(/отдельный документ по ним не формируется/)).toBeInTheDocument()
  })
})

describe('Attendance dashboard (read-only, KPI rules)', () => {
  const now = new Date()
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const lesson = (id: number, day: string, start: string, extra: Record<string, unknown> = {}) => ({
    ...lesson18(), id, date: `${ym}-${day}`, start, end: '17:30', lesson_number: id, topic: `Тема ${id}`,
    teacher: { id: 1, name: 'Ислам' }, comment: '', excuse_reason: '', state: 'present' as const, ...extra,
  })
  const stats = { marked: 6, present: 3, late: 1, absent: 1, excused: 1, attended: 4, missed: 2, percent: 66.7 }

  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
    vi.mocked(studentPortalApi.attendanceOverview).mockResolvedValue({
      rules: { attended: ['present', 'late'], missed: ['absent', 'excused'], percent: 'attended / marked', unmarked_counts_as_missed: false, cancelled_counts: false },
      summary: { ...stats, held: 7, unmarked: 1 },
      streak: { current: 2, best: 3 },
      months: [{ year: now.getFullYear(), month: now.getMonth() + 1, ...stats }],
      subjects: [{ subject: 'Python', ...stats }],
      weeks: [{ start: `${ym}-01`, end: `${ym}-07`, ...stats }],
      since: `${ym}-01`,
    })
    vi.mocked(studentPortalApi.attendance).mockResolvedValue({
      year: now.getFullYear(), month: now.getMonth() + 1, today: `${ym}-15`, summary: stats,
      lessons: [
        lesson(1, '03', '10:00', { state: 'present', attendance: 'present' }),
        lesson(2, '03', '16:00', { state: 'late', attendance: 'late', subject: { id: 2, name: 'English' } }),
        lesson(3, '05', '16:00', { state: 'absent', attendance: 'absent' }),
        lesson(4, '07', '16:00', { state: 'excused', attendance: 'excused', excuse_reason: 'Болел' }),
      ],
    })
    vi.mocked(studentPortalApi.attendanceHistory).mockResolvedValue({ count: 1, next: null, previous: null, results: [
      { id: 9, status: 'absent', comment: '', excuse_reason: '', lesson: { ...lesson18(), date: `${ym}-05`, teacher: { id: 1, name: 'Ислам' } } },
    ] })
  })

  function renderAttendance() {
    return renderWithProviders(
      <Routes><Route path="/student" element={<StudentPortalLayout />}><Route path="attendance" element={<StudentAttendancePage />} /></Route></Routes>,
      { route: '/student/attendance' },
    )
  }

  it('shows the real totals and explains the rules', async () => {
    renderAttendance()
    expect(await screen.findByText('4 из 6 отмеченных')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Общая посещаемость 67%/ })).toBeInTheDocument()
    expect(screen.getByText('Без отметки: 1')).toBeInTheDocument()
    expect(screen.getByText(/Посещено = «был» \+ «опоздал»/)).toBeInTheDocument()
    expect(screen.getByText('2 подряд')).toBeInTheDocument()
  })

  it('colours the calendar by status and lists every lesson of a day', async () => {
    renderAttendance()
    const day3 = await screen.findByRole('button', { name: `${ym}-03: Был, Опоздал` })
    expect(day3.className).toContain('bg-brand-50') // present → green
    expect(screen.getByRole('button', { name: `${ym}-05: Не был` }).className).toContain('bg-danger-soft') // red
    expect(screen.getByRole('button', { name: `${ym}-07: Уважительная причина` }).className).toContain('bg-info-soft') // blue
    await userEvent.setup().click(day3)
    expect((await screen.findAllByText('Занятий: 2')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('English').length).toBeGreaterThan(0)
  })

  it('navigates months and filters the history', async () => {
    renderAttendance()
    await screen.findByText('4 из 6 отмеченных')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    await waitFor(() => expect(studentPortalApi.attendance).toHaveBeenLastCalledWith(1, prev.getFullYear(), prev.getMonth() + 1))
    await user.click(screen.getByRole('button', { name: /^Не был$/ }))
    await waitFor(() => expect(studentPortalApi.attendanceHistory).toHaveBeenLastCalledWith(1, 'absent', 1))
    expect(screen.queryByRole('button', { name: /Отметить|Сохранить/ })).not.toBeInTheDocument() // read-only
  })

  it('speaks Kyrgyz', async () => {
    window.localStorage.setItem('okk-student-portal-lang', 'ky')
    renderAttendance()
    expect(await screen.findByText('6 белгиленгендин 4')).toBeInTheDocument()
    expect(screen.getByText('Катышуу календары')).toBeInTheDocument()
  })
})
