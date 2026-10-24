import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { UserRole } from '@/types/auth'
import type { ContractCard, FinanceMe, FinanceOptions, Payment, QueueRow, Receipt } from '@/types/finance'

const mockRole = vi.hoisted(() => ({ role: 'accountant' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/accounting', () => ({ newIdempotencyKey: () => 'form-key' }))
vi.mock('@/api/finance', () => ({
  financeApi: {
    me: vi.fn(), options: vi.fn(), counts: vi.fn(), queue: vi.fn(), card: vi.fn(), previewPayment: vi.fn(),
    recordPayment: vi.fn(), receipt: vi.fn(), receiptPrinted: vi.fn(), downloadReceiptPdf: vi.fn(), plans: vi.fn(),
    lmsStudents: vi.fn(), createContract: vi.fn(), periods: vi.fn(), payments: vi.fn(), periodReport: vi.fn(),
  },
}))

import { financeApi } from '@/api/finance'
import { AddPaymentPage } from '@/features/finance/AddPaymentPage'
import { FinanceLayout } from '@/features/finance/FinanceLayout'
import { NewContractPage } from '@/features/finance/NewContractPage'
import { PaymentsPage } from '@/features/finance/PaymentsPage'
import { currentMonth, setFinancePeriod } from '@/features/finance/period'
import { ToPayPage } from '@/features/finance/QueuePage'
import { ReceiptSheet } from '@/features/finance/ReceiptPage'

const ACCOUNTANT: FinanceMe = {
  role: 'accountant', read_only: false, can_view: true, can_view_money: true, is_manager: false, is_accountant: true,
  is_director: false, can_record_payments: true, can_register: true, can_manage_plans: true, can_manage_settings: true,
  can_view_audit: true, max_manager_discount_percent: '10',
}
const DIRECTOR: FinanceMe = {
  ...ACCOUNTANT, role: 'director', read_only: true, is_accountant: false, is_director: true, can_record_payments: false,
  can_register: false, can_manage_plans: false, can_manage_settings: false,
}
const MANAGER: FinanceMe = {
  ...ACCOUNTANT, role: 'manager', can_view_money: false, is_accountant: false, is_manager: true, can_record_payments: false,
  can_manage_plans: false, can_manage_settings: false, can_view_audit: false,
}

const OPTIONS = {
  plans: [], programs: [{ id: 1, name: "Kid's Club" }], subjects: [], groups: [], accountants: [], invoice_statuses: [],
  payment_methods: [{ value: 'cash', label: 'Наличные' }], payment_modes: [], reservation_modes: [], contract_statuses: [],
  contact_channels: [], contact_results: [],
} as FinanceOptions

const ROW: QueueRow = {
  profile: 7, student: 3, student_name: 'Асанов Айбек', group: 1, group_name: 'KC-1', program: "Kid's Club", plan: 1,
  plan_name: "Kid's Club Standard", subject_name: 'IT', parent_name: 'Асанова А.', parent_phone: '+996555000111',
  contract_status: 'ACTIVE', contract_status_display: 'Обучается', is_course: true, payment_mode: 'MONTHLY',
  payment_mode_display: 'Помесячная оплата', duration_months: 4, month_number: 2, lessons_used: 1, lessons_total: 12,
  final_course_price: '60000.00', discount_amount: '0.00', stage: 'awaiting',
  focus_invoice: { id: 31, number: 'INV-2026-000031', kind: 'MONTH', month_number: 2, amount: '15000.00', paid: '5000.00',
    balance: '10000.00', due_lesson: 3, due_date: null, status: 'PARTIALLY_PAID', status_display: 'Частично оплачено' },
  due_now: '10000.00', overdue_amount: '0.00', overdue_lessons: 0, overdue_days: 0, credit: '0.00',
  last_contact_at: null, last_contact_result: null,
}

beforeEach(() => {
  vi.clearAllMocks()
  mockRole.role = 'accountant'
  vi.mocked(financeApi.me).mockResolvedValue(ACCOUNTANT)
  vi.mocked(financeApi.options).mockResolvedValue(OPTIONS)
  vi.mocked(financeApi.counts).mockResolvedValue({ to_pay: 4, soon: 2, overdue: 3 })
  vi.mocked(financeApi.queue).mockResolvedValue({ count: 1, page: 1, page_size: 25, results: [ROW] })
  vi.mocked(financeApi.periods).mockResolvedValue({ today: '2026-10-24', current: '2026-10', months: [
    { value: '2026-11', label: 'Ноябрь 2026', date_from: '2026-11-01', date_to: '2026-11-30', is_current: false },
    { value: '2026-10', label: 'Октябрь 2026', date_from: '2026-10-01', date_to: '2026-10-31', is_current: true },
    { value: '2026-09', label: 'Сентябрь 2026', date_from: '2026-09-01', date_to: '2026-09-30', is_current: false },
  ] })
  vi.mocked(financeApi.payments).mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
  setFinancePeriod({ kind: 'month', month: currentMonth() })
})

describe('FinanceLayout', () => {
  it('gives the accountant the full sidebar with queue badges', async () => {
    renderWithProviders(<Routes><Route path="/finance/*" element={<FinanceLayout />} /></Routes>, { route: '/finance' })
    const nav = await screen.findByRole('navigation', { name: 'Финансы студентов' })
    await waitFor(() => expect(nav).toHaveTextContent('Настройки'))
    for (const label of ['Dashboard', 'К оплате', 'Скоро оплата', 'Просроченные', 'Все студенты', 'Платежи', 'Чеки',
      'Аналитика', 'Тарифы и программы', 'Журнал операций', 'Настройки']) {
      expect(nav).toHaveTextContent(label)
    }
    expect(await screen.findByLabelText('3 студентов')).toHaveTextContent('3')
  })

  it('switches the finance period to a past month or a custom range', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Routes><Route path="/finance/*" element={<FinanceLayout />} /></Routes>, { route: '/finance' })
    const switcher = await screen.findByLabelText('Финансовый период')
    await screen.findByRole('option', { name: 'Сентябрь 2026' })
    expect(screen.getByRole('option', { name: 'Ноябрь 2026' })).toBeInTheDocument()
    await user.selectOptions(switcher, '2026-09')
    expect(switcher).toHaveValue('2026-09')
    await user.selectOptions(switcher, 'range')
    expect(screen.getByLabelText('Начало периода')).toHaveValue('2026-09-01')
    expect(screen.getByLabelText('Конец периода')).toHaveValue('2026-09-30')
  })

  it('hides tariffs and settings from the read-only director', async () => {
    mockRole.role = 'director'
    vi.mocked(financeApi.me).mockResolvedValue(DIRECTOR)
    renderWithProviders(<Routes><Route path="/finance/*" element={<FinanceLayout />} /></Routes>, { route: '/finance' })
    const nav = await screen.findByRole('navigation', { name: 'Финансы студентов' })
    await waitFor(() => expect(nav).toHaveTextContent('Аналитика'))
    expect(nav).not.toHaveTextContent('Тарифы и программы')
    expect(nav).not.toHaveTextContent('Настройки')
    expect(nav).toHaveTextContent('Журнал операций')
  })

  it('shows the manager only the students section', async () => {
    mockRole.role = 'assistant'
    vi.mocked(financeApi.me).mockResolvedValue(MANAGER)
    renderWithProviders(<Routes><Route path="/finance/*" element={<FinanceLayout />} /></Routes>, { route: '/finance' })
    const nav = await screen.findByRole('navigation', { name: 'Финансы студентов' })
    await waitFor(() => expect(nav).toHaveTextContent('Все студенты'))
    expect(nav).not.toHaveTextContent('Платежи')
    expect(financeApi.counts).not.toHaveBeenCalled()
  })
})

describe('PaymentsPage', () => {
  it('lists payments received in the selected (past) period', async () => {
    setFinancePeriod({ kind: 'month', month: '2026-09' })
    renderWithProviders(<PaymentsPage />)
    await waitFor(() => expect(financeApi.payments).toHaveBeenCalled())
    expect(vi.mocked(financeApi.payments).mock.calls[0][0]).toMatchObject({ date_from: '2026-09-01', date_to: '2026-09-30' })
    expect(await screen.findByText(/Сентябрь 2026/)).toBeInTheDocument()
  })
})

describe('«К оплате»', () => {
  it('shows month progress, charge, received, balance and the lesson deadline', async () => {
    renderWithProviders(<ToPayPage />)
    const row = (await screen.findByText('Асанов Айбек')).closest('tr')!
    expect(row).toHaveTextContent('Месяц 2 из 4')
    expect(row).toHaveTextContent('IT 1 из 12')
    expect(row).toHaveTextContent('15 000 сом')
    expect(row).toHaveTextContent('5 000 сом')
    expect(row).toHaveTextContent('10 000 сом')
    expect(row).toHaveTextContent('3-й урок IT месяца 2')
    expect(row).toHaveTextContent('Ожидается оплата')
    expect(row.querySelector('button')).toHaveTextContent('Платёж')
  })

  it('offers no payment action to the director', async () => {
    vi.mocked(financeApi.me).mockResolvedValue(DIRECTOR)
    renderWithProviders(<ToPayPage />)
    const row = (await screen.findByText('Асанов Айбек')).closest('tr')!
    await waitFor(() => expect(financeApi.me).toHaveBeenCalled())
    expect(row).not.toHaveTextContent('Платёж')
  })
})

const CARD = {
  contract: { id: 7, student_name: 'Асанов Айбек', parent_name: 'Асанова А.', payment_mode_display: 'Помесячная оплата',
    final_course_price: '60000.00', discount_enabled: false, discount_amount: '0.00' },
  row: ROW,
  summary: { due_now: '10000.00', overdue: '0.00', credit: '0.00', outstanding: '45000.00' },
  invoices: [{ id: 31, number: 'INV-2026-000031', kind: 'MONTH', month_number: 2, package_number: 2, status: 'PARTIALLY_PAID',
    amount: '15000.00', balance: '10000.00', period_date: '2026-09-01' }],
} as unknown as ContractCard

describe('AddPaymentPage', () => {
  it('previews the result and saves one payment per open form even on a double click', async () => {
    vi.mocked(financeApi.card).mockResolvedValue(CARD)
    vi.mocked(financeApi.previewPayment).mockResolvedValue({
      amount: '10000.00', obligation: '15000.00', paid_before: '5000.00', obligation_balance_after: '0.00', to_credit: '0.00',
      due_now_before: '10000.00', due_now_after: '0.00', credit_before: '0.00', credit_after: '0.00',
      outstanding_before: '45000.00', outstanding_after: '35000.00', allocations: [],
    })
    let resolve: (p: Payment) => void = () => undefined
    vi.mocked(financeApi.recordPayment).mockReturnValue(new Promise((r) => { resolve = r }))
    const user = userEvent.setup()
    renderWithProviders(<AddPaymentPage />, { route: '/finance/payments/new?profile=7' })
    expect(await screen.findByLabelText(/Получено, сом/)).toHaveValue('10000.00')
    expect(await screen.findByText('Сумма обязательства')).toBeInTheDocument()
    expect(screen.getByText('35 000 сом')).toBeInTheDocument()
    await user.click(screen.getByLabelText('Деньги фактически получены'))
    const save = screen.getByRole('button', { name: 'Сохранить платёж' })
    await user.click(save)
    await user.click(save)
    expect(financeApi.recordPayment).toHaveBeenCalledTimes(1)
    const [body, key] = vi.mocked(financeApi.recordPayment).mock.calls[0]
    expect(body).toMatchObject({ profile: 7, amount: '10000.00', mode: 'auto', method: 'cash' })
    expect(key).toBe('form-key')
    resolve({ id: 1, billing_profile: 7, student_name: 'Асанов Айбек', amount: '10000.00', method_display: 'Наличные',
      receipt: { id: 9, number: 'OK-2026-000009', status: 'ISSUED' } } as Payment)
    expect(await screen.findByRole('heading', { name: 'Платёж сохранён' })).toBeInTheDocument()
    for (const name of ['Печать чека', 'Скачать PDF', 'Добавить следующий платёж', 'Открыть карточку студента']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('records a payment actually received in September with its own date and purpose', async () => {
    vi.mocked(financeApi.card).mockResolvedValue(CARD)
    vi.mocked(financeApi.previewPayment).mockResolvedValue({
      amount: '10000.00', obligation: '15000.00', paid_before: '5000.00', obligation_balance_after: '0.00', to_credit: '0.00',
      due_now_before: '10000.00', due_now_after: '0.00', credit_before: '0.00', credit_after: '0.00',
      outstanding_before: '45000.00', outstanding_after: '35000.00',
      allocations: [{ invoice: 31, number: 'INV-2026-000031', month_number: 2, payment: '10000.00', balance_after: '0.00' }],
    })
    vi.mocked(financeApi.recordPayment).mockResolvedValue({ id: 2, billing_profile: 7, student_name: 'Асанов Айбек',
      amount: '10000.00', method_display: 'Наличные', receipt: null } as Payment)
    const user = userEvent.setup()
    renderWithProviders(<AddPaymentPage />, { route: '/finance/payments/new?profile=7' })
    const date = await screen.findByLabelText('Дата фактического получения')
    await user.clear(date)
    await user.type(date, '2026-09-20')
    expect(screen.getByText(/Поступление за Сентябрь 2026/)).toBeInTheDocument()
    expect(await screen.findByText(/за Сентябрь 2026\)/)).toBeInTheDocument()  // гасит сентябрьское начисление
    await user.click(screen.getByLabelText('Деньги фактически получены'))
    await user.click(screen.getByRole('button', { name: 'Сохранить платёж' }))
    expect(vi.mocked(financeApi.recordPayment).mock.calls[0][0]).toMatchObject({
      received_date: '2026-09-20', purpose: 'tuition', mode: 'auto',
    })
  })
})

describe('NewContractPage', () => {
  it('computes the discount in som from the final course price', async () => {
    vi.mocked(financeApi.plans).mockResolvedValue({ count: 1, next: null, previous: null, results: [{
      id: 1, name: "Kid's Club Standard", subject: 1, subject_name: 'IT', course: 1, course_name: "Kid's Club",
      duration_months: 4, payment_deadline_lessons: 3, allow_monthly: true, allow_full_prepay: true, absence_policy: 'ALL_HELD',
      is_active: true, current: { lessons_per_package: 12, package_price: '15000.00', effective_from: '2026-01-01', standard_course_price: '60000.00' },
    }] })
    vi.mocked(financeApi.lmsStudents).mockResolvedValue({ count: 1, next: null, previous: null, results: [
      { id: 3, name: 'Асанов Айбек', group: 1, group_name: 'KC-1', status: 'active', status_display: 'Активен', parent_phone: '', profiles: [] },
    ] })
    const user = userEvent.setup()
    renderWithProviders(<NewContractPage />, { route: '/finance/contracts/new?student=3' })
    await screen.findByRole('option', { name: "Kid's Club Standard" })
    await user.selectOptions(screen.getByLabelText(/Программа/), '1')
    expect(screen.getByLabelText('Стандартная стоимость курса')).toHaveValue('60\u00a0000\u00a0сом')
    await user.click(screen.getByLabelText('Скидка предоставлена'))
    await user.type(screen.getByLabelText('Итоговая стоимость курса'), '45000')
    expect(screen.getByLabelText('Размер скидки в сомах')).toHaveValue('15\u00a0000\u00a0сом')
  })
})

describe('ReceiptSheet', () => {
  it('prints the real logo, the operation data and says it is not a fiscal receipt', () => {
    const receipt = {
      id: 9, number: 'OK-2026-000009', kind: 'PAYMENT', status: 'ISSUED', amount: '10000.00', issued_at: '2026-10-21T10:00:00Z',
      rows: [{ label: 'Студент', value: 'Асанов Айбек' }, { label: 'Сумма платежа', value: '10 000,00 сом' },
        { label: 'Остаток долга по договору', value: '35 000,00 сом' }],
      academy: { name: 'Okurmen Kids', details: 'Бишкек', footer: 'Спасибо!' },
    } as Receipt
    renderWithProviders(<ReceiptSheet receipt={receipt} />)
    expect(screen.getByAltText('Okurmen Kids')).toBeInTheDocument()
    expect(screen.getByText('Чек об оплате № OK-2026-000009')).toBeInTheDocument()
    expect(screen.getByText('10 000,00 сом')).toBeInTheDocument()
    expect(screen.getByText('35 000,00 сом')).toBeInTheDocument()
    expect(screen.getByText(/Не является фискальным чеком/)).toBeInTheDocument()
  })
})
