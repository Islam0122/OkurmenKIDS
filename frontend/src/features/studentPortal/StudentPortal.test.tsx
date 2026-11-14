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
    vi.mocked(studentPortalApi.achievements).mockResolvedValue({
      xp: {
        total: { attendance: 300, homework: 700, tests: 65, total: 1065 },
        month: { attendance: 15, homework: 53, tests: 0, total: 68 },
        level: { level: 5, floor: 1000, next: 1500, progress: 13 },
      },
      earned: [{ code: 'homework_streak', date: null, params: { count: 20 } }],
      milestones: [
        { code: 'homework_streak', current: 42, target: 50 },
        { code: 'top_homework', current: 25, target: null },
      ],
    })
    renderWithProviders(
      <Routes><Route path="/student" element={<StudentPortalLayout />}><Route path="achievements" element={<StudentAchievementsPage />} /></Route></Routes>,
      { route: '/student/achievements' },
    )
    expect(await screen.findByText('1065')).toBeInTheDocument()
    expect(screen.getByText('20+ сданных заданий')).toBeInTheDocument()
    expect(screen.getByText('Сдать 50 заданий')).toBeInTheDocument()
    expect(screen.getByText('42/50')).toBeInTheDocument()
    expect(screen.getByText('Все награды этого вида получены!')).toBeInTheDocument()
    // Navigation: the achievements section is in the menu.
    expect(screen.getAllByRole('link', { name: 'Достижения' }).length).toBeGreaterThan(0)
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
