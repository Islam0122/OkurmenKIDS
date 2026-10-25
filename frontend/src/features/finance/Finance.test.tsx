import { screen, waitFor, within } from '@testing-library/react'
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
    lessonBreakdown: vi.fn(), applyCredit: vi.fn(), changeStartDate: vi.fn(),
    payment: vi.fn(), paymentHistory: vi.fn(), correctPayment: vi.fn(), reversePayment: vi.fn(), saveMonthPlan: vi.fn(), prepayments: vi.fn(),
  },
}))

import { financeApi } from '@/api/finance'
import { AddPaymentPage } from '@/features/finance/AddPaymentPage'
import { FinanceLayout } from '@/features/finance/FinanceLayout'
import { NewContractPage } from '@/features/finance/NewContractPage'
import { PaymentDetailPage } from '@/features/finance/PaymentDetailPage'
import { PaymentsPage } from '@/features/finance/PaymentsPage'
import { PrepaymentsPage } from '@/features/finance/PrepaymentsPage'
import { StudentCardPage } from '@/features/finance/StudentCardPage'
import { currentMonth, setFinancePeriod } from '@/features/finance/period'
import { OperationsTable, ScheduleBlock } from '@/features/finance/CardSections'
import { ToPayPage } from '@/features/finance/QueuePage'
import { ReceiptSheet } from '@/features/finance/ReceiptPage'
import { MonthProgress, rowProgress } from '@/features/finance/ui'

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

describe('StudentCardPage', () => {
  it('shows unapplied credit separately and explains every attendance', async () => {
    vi.mocked(financeApi.card).mockResolvedValue({
      ...CARD,
      contract: { ...CARD.contract, status: 'ACTIVE', status_display: 'Обучается', is_course: true, start_date: '2026-10-24' },
      summary: { received: '53000.00', refunded: '0.00', net_received: '53000.00', reservation_received: '0.00',
        reservation_unused: '0.00', allocated: '0.00', adjusted: '0.00', credit: '53000.00', invoiced: '53000.00',
        invoices_balance: '53000.00', credit_applicable: '53000.00', credit_unapplied: '53000.00', due_now: '0.00',
        overdue: '0.00', paid_total: '53000.00', standard_course_price: '60000.00', final_course_price: '53000.00',
        discount_amount: '7000.00', outstanding: '0.00', future: '0.00' },
      months: [], invoices: [], reservations: [], payments: [], contacts: [],
    } as unknown as ContractCard)
    vi.mocked(financeApi.lessonBreakdown).mockResolvedValue({
      attended: 2, marked: 2, counted: 0, priority_subject: 'IT', contract_start: '2026-10-24',
      totals: { other_subject: 1, before_contract: 1 }, priority_before_contract: { count: 1, first_date: '2026-09-08' },
      lessons: [
        { lesson: 1, date: '2026-09-08', group: 'KC-1', subject: 'IT', lesson_status: 'completed', lesson_status_display: 'Проведён',
          attendance: 'present', attendance_display: 'Присутствовал', contract_start: '2026-10-24', reason: 'before_contract',
          reason_display: 'До даты начала договора', month_number: null },
        { lesson: 2, date: '2026-09-09', group: 'KC-1', subject: 'English', lesson_status: 'completed', lesson_status_display: 'Проведён',
          attendance: 'present', attendance_display: 'Присутствовал', contract_start: '2026-10-24', reason: 'other_subject',
          reason_display: 'Другой предмет', month_number: null },
      ],
    })
    const user = userEvent.setup()
    renderWithProviders(<Routes><Route path="/finance/students/:profileId" element={<StudentCardPage />} /></Routes>,
      { route: '/finance/students/7' })
    expect(await screen.findByText(/Свободный аванс 53 000 сом не распределён/)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Распределить аванс' })).toBeInTheDocument()
    expect(screen.getByText('Получено по договору')).toBeInTheDocument()
    expect(await screen.findByText(/1 проведённых уроков IT до даты начала договора/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Разбор посещений' }))
    const table = screen.getByRole('table')
    expect(table).toHaveTextContent('Причина учёта или исключения')
    expect(table).toHaveTextContent('Другой предмет')
    expect(table).toHaveTextContent('До даты начала договора')
    await user.click(screen.getByRole('button', { name: 'Распределить аванс' }))
    expect(financeApi.applyCredit).toHaveBeenCalledWith(7)
  })
})

const PAYMENT = {
  id: 5, billing_profile: 7, student: 3, student_name: 'Абдыбеков Бекнур', group_name: 'KC-1', program_name: "Kid's Club",
  kind: 'payment', purpose: 'tuition', purpose_display: 'Оплата обучения', amount: '53000.00', received_date: '2026-10-24',
  method: 'cash', method_display: 'Наличные', reference: '', comment: '', status: 'confirmed', void_reason: '',
  unallocated: '0.00', created_by_name: 'Демо Бухгалтер', created_at: '2026-10-24T08:00:00Z',
  receipt: { id: 9, number: 'OK-2026-000008', status: 'ISSUED' },
  allocations: [{ id: 1, invoice: 83, invoice_number: 'INV-2026-000083', invoice_period_date: '2026-09-01', amount: '53000.00', status: 'ACTIVE' }],
} as unknown as Payment

describe('PaymentDetailPage', () => {
  const open = () => renderWithProviders(<Routes><Route path="/finance/payments/:paymentId" element={<PaymentDetailPage />} /></Routes>,
    { route: '/finance/payments/5' })

  beforeEach(() => {
    vi.mocked(financeApi.payment).mockResolvedValue(PAYMENT)
    vi.mocked(financeApi.paymentHistory).mockResolvedValue([{ id: 1, created_at: '2026-10-24T08:00:00Z', actor: 'buh',
      action: 'billing_payment_correct', entity_type: 'studentpayment', entity_id: 5,
      old_values: { received_date: '2026-10-24' }, new_values: { received_date: '2026-09-08' }, reason: 'Дата 08.09' }])
  })

  it('lets the accountant fix the received date sending only the changed field', async () => {
    vi.mocked(financeApi.correctPayment).mockResolvedValue({ payment: PAYMENT, changed: ['received_date'], warnings: [], audit: 1 })
    const user = userEvent.setup()
    open()
    expect(await screen.findByText(/OK-2026-000008/)).toBeInTheDocument()
    expect(screen.getByText(/Повторная печать не создаёт/)).toBeInTheDocument()
    expect(await screen.findByText('Исправление платежа')).toBeInTheDocument()  // история
    await user.click(await screen.findByRole('button', { name: 'Исправить дату' }))
    const date = screen.getByLabelText('Дата фактического поступления денег')
    await user.clear(date)
    await user.type(date, '2026-09-08')
    expect(screen.getByText(/переедет из «Октябрь 2026» в «Сентябрь 2026»/)).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled()  // без причины нельзя
    await user.type(screen.getByLabelText(/Причина корректировки/), 'Деньги получены 08.09')
    await user.click(save)
    expect(financeApi.correctPayment).toHaveBeenCalledWith(5, { reason: 'Деньги получены 08.09', received_date: '2026-09-08',
      confirm_closed_period: false })
  })

  it('confirms voiding with payment details and a reason', async () => {
    vi.mocked(financeApi.reversePayment).mockResolvedValue(PAYMENT)
    const user = userEvent.setup()
    open()
    await user.click(await screen.findByRole('button', { name: 'Аннулировать' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('№5 · чек OK-2026-000008')
    expect(dialog).toHaveTextContent('Абдыбеков Бекнур')
    await user.type(screen.getByLabelText(/Причина/), 'Внесён дважды')
    await user.click(within(dialog).getByRole('button', { name: 'Аннулировать' }))
    expect(financeApi.reversePayment).toHaveBeenCalledWith(5, 'Внесён дважды')
  })

  it('shows the director a read-only payment', async () => {
    vi.mocked(financeApi.me).mockResolvedValue(DIRECTOR)
    open()
    expect(await screen.findByText(/OK-2026-000008/)).toBeInTheDocument()
    await waitFor(() => expect(financeApi.me).toHaveBeenCalled())
    for (const name of ['Редактировать', 'Исправить дату', 'Аннулировать']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })
})

describe('StudentCardPage — бронь и платежи', () => {
  it('shows one row per operation, the reservation as the same payment and a consistent schedule', async () => {
    const payment = { ...PAYMENT, id: 28, purpose: 'reservation', purpose_display: 'Бронь', method: 'bank',
      method_display: 'Банковский перевод', received_date: '2026-08-25', amount: '38000.00', unallocated: '18000.00',
      receipt: { id: 3, number: 'OK-2026-000028', status: 'ISSUED' },
      allocations: [
        { id: 1, invoice: 100, invoice_number: 'INV-2026-000100', invoice_period_date: '2026-09-09', amount: '10000.00', status: 'ACTIVE' },
        { id: 2, invoice: 101, invoice_number: 'INV-2026-000101', invoice_period_date: '2026-10-01', amount: '10000.00', status: 'ACTIVE' },
      ] } as unknown as Payment
    vi.mocked(financeApi.lessonBreakdown).mockResolvedValue({ attended: 0, marked: 0, counted: 0, priority_subject: 'IT',
      contract_start: '2026-09-09', totals: {}, priority_before_contract: { count: 0, first_date: null }, lessons: [] })
    vi.mocked(financeApi.card).mockResolvedValue({
      ...CARD,
      contract: { ...CARD.contract, status: 'ACTIVE', status_display: 'Обучается', is_course: true, start_date: '2026-09-09' },
      summary: { received: '38000.00', refunded: '0.00', net_received: '38000.00', reservation_received: '38000.00',
        reservation_unused: '18000.00', allocated: '20000.00', adjusted: '0.00', credit: '18000.00', invoiced: '20000.00',
        invoices_balance: '0.00', credit_applicable: '18000.00', credit_unapplied: '0.00', due_now: '0.00', overdue: '0.00',
        paid_total: '38000.00', standard_course_price: '60000.00', final_course_price: '38000.00', discount_amount: '22000.00',
        outstanding: '0.00', future: '18000.00' },
      reservations: [{ id: 4, expected_amount: '38000.00', status: 'PAID', payment: 28, paid_amount: '38000.00',
        paid_date: '2026-08-25', receipt_number: 'OK-2026-000028', paid_used: '20000.00', paid_unused: '18000.00', reserved_until: null }],
      schedule: { final_course_price: '38000.00', invoiced: '20000.00', projected: '18000.00', total: '38000.00', consistent: true,
        issues: [], price_changes: [{ date: '2026-10-24', from: '40000.00', to: '38000.00', reason: 'Доп. скидка' }],
        months: [
          { month_number: 1, state: 'invoiced', invoice: 100, number: 'INV-2026-000100', amount: '10000.00', paid: '10000.00', balance: '0.00', covered_by_credit: '0.00', to_pay: '0.00' },
          { month_number: 2, state: 'invoiced', invoice: 101, number: 'INV-2026-000101', amount: '10000.00', paid: '10000.00', balance: '0.00', covered_by_credit: '0.00', to_pay: '0.00' },
          { month_number: 3, state: 'future', amount: '9000.00', paid: '0.00', balance: '0.00', covered_by_credit: '9000.00', to_pay: '0.00' },
          { month_number: 4, state: 'future', amount: '9000.00', paid: '0.00', balance: '0.00', covered_by_credit: '9000.00', to_pay: '0.00' },
        ] },
      months: [], invoices: [], payments: [payment], contacts: [],
    } as unknown as ContractCard)
    renderWithProviders(<Routes><Route path="/finance/students/:profileId" element={<StudentCardPage />} /></Routes>,
      { route: '/finance/students/7' })
    const table = await screen.findByRole('table', { name: 'Платежи и чеки' })
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(2)  // заголовок + одна операция
    expect(rows[0]).toHaveTextContent('ДатаТип операцииСуммаСпособ оплатыСтатусКто принялНомер чекаДействия')
    expect(rows[1]).toHaveTextContent('25.08.2026')
    expect(rows[1]).toHaveTextContent('Бронь')
    expect(rows[1]).toHaveTextContent('Банковский перевод')
    expect(rows[1]).toHaveTextContent('OK-2026-000028')
    const reservation = screen.getByText(/Это тот же платёж/)
    expect(reservation).toHaveTextContent('Оплачена платежом №28 от 25.08.2026 (чек OK-2026-000028)')
    expect(reservation).toHaveTextContent(/засчитано в начисления 20\s000 сом, осталось авансом 18\s000 сом/)
    expect(screen.getByText(/= итоговая стоимость 38\s000/)).toBeInTheDocument()
    const schedule = screen.getByRole('table', { name: 'График оплаты' })
    expect(within(schedule).getAllByRole('row')).toHaveLength(5)
    expect(schedule).toHaveTextContent('будет выставлен')
  })
})

describe('Учебный месяц — из backend, 12/12 в завершённом месяце', () => {
  const base = { month_number: 1, duration_months: 6, lessons_used: 12, lessons_total: 12, course_lessons_counted: 12,
    course_lessons_total: 72, billing_month_number: 2, next_month_open: true } as QueueRow

  it('boundary: «Месяц 1 из 6 · IT 12 из 12 · курс 12 из 72» and the issued next month as a hint', () => {
    renderWithProviders(<MonthProgress {...rowProgress(base)} />)
    expect(screen.getByText('Месяц 1 из 6')).toBeInTheDocument()
    expect(screen.getByText('IT 12 из 12')).toBeInTheDocument()
    expect(screen.getByText('курс 12 из 72')).toBeInTheDocument()
    expect(screen.getByText('выставлен месяц 2')).toBeInTheDocument()
  })

  it('14 lessons: «Месяц 2 из 6 · IT 2 из 12 · курс 14 из 72», no hint', () => {
    renderWithProviders(<MonthProgress {...rowProgress({ ...base, month_number: 2, lessons_used: 2,
      course_lessons_counted: 14, next_month_open: false })} />)
    expect(screen.getByText('Месяц 2 из 6')).toBeInTheDocument()
    expect(screen.getByText('IT 2 из 12')).toBeInTheDocument()
    expect(screen.getByText('курс 14 из 72')).toBeInTheDocument()
    expect(screen.queryByText(/выставлен месяц/)).not.toBeInTheDocument()
  })

  it('card separates the student’s counted lessons from the group’s held lessons', async () => {
    vi.mocked(financeApi.lessonBreakdown).mockResolvedValue({ attended: 0, marked: 0, counted: 0, priority_subject: 'IT',
      contract_start: '2026-09-04', totals: {}, priority_before_contract: { count: 0, first_date: null }, lessons: [] })
    vi.mocked(financeApi.card).mockResolvedValue({
      ...CARD, schedule: null, invoices: [], payments: [], contacts: [], reservations: [],
      contract: { ...CARD.contract, status: 'ACTIVE', status_display: 'Обучается', is_course: true, subject_name: 'IT' },
      progress: { month: 1, months: 6, in_month: 12, per_month: 12, counted: 12, total: 72, billing_month: 2,
        next_month_open: true, group_held: { all_time: 14, since_contract: 12 } },
      months: [
        { id: 1, number: 1, month_number: 1, status: 'COMPLETED', lessons_total: 12, lessons_used: 12, lessons_remaining: 0,
          final_price: '12000.00', started_on: '2026-09-04', completed_on: '2026-10-20', invoice: null, is_current: true },
        { id: 2, number: 2, month_number: 2, status: 'ACTIVE', lessons_total: 12, lessons_used: 0, lessons_remaining: 12,
          final_price: '12000.00', started_on: null, completed_on: null, invoice: null, is_current: false },
      ],
    } as unknown as ContractCard)
    renderWithProviders(<Routes><Route path="/finance/students/:profileId" element={<StudentCardPage />} /></Routes>,
      { route: '/finance/students/7' })
    const line = await screen.findByTestId('study-progress')
    expect(line).toHaveTextContent('Учебный месяц 1 из 6 · IT 12 из 12')
    expect(line).toHaveTextContent('засчитано ученику за курс 12 из 72')
    expect(line).toHaveTextContent('проведено занятий IT в группе с начала договора: 12 (всего 14)')
    expect(line).toHaveTextContent('начисление за месяц 2 уже выставлено')
    expect(screen.getByText('Текущий (пройден)')).toBeInTheDocument()
    expect(screen.getByText('Выставлен, уроков ещё нет')).toBeInTheDocument()
  })
})

describe('StudentCardPage — предоплата за весь курс и кнопка «Добавить платёж»', () => {
  const SUMMARY = { received: '53000.00', refunded: '0.00', net_received: '53000.00', reservation_received: '0.00',
    reservation_unused: '0.00', allocated: '53000.00', adjusted: '0.00', credit: '0.00', invoiced: '53000.00',
    invoices_balance: '0.00', credit_applicable: '0.00', credit_unapplied: '0.00', due_now: '0.00', overdue: '0.00',
    paid_total: '53000.00', standard_course_price: '60000.00', final_course_price: '53000.00', discount_amount: '7000.00',
    outstanding: '0.00', future: '0.00', net_to_pay: '0.00', voided: '0.00', voided_count: 0, credit_reserved_future: '0.00',
    credit_unreserved: '0.00', course_paid_in_full: true }
  const share = (n: number, paid: string, state: 'prepaid' | 'course_due') => ({ month_number: n, state, kind: 'COURSE',
    invoice: 50, number: 'INV-2026-000050', amount: '13250.00', paid, balance: '0.00', covered_by_credit: '0.00',
    to_pay: '0.00', standard_price: null, plan_amount: null, status: 'PAID', status_display: 'Оплачено' })
  const prepaidCard = (paidInFull = true) => ({
    ...CARD,
    contract: { ...CARD.contract, status: 'ACTIVE', status_display: 'Обучается', is_course: true, payment_mode: 'FULL_PREPAY',
      payment_mode_display: 'Предоплата за весь курс', final_course_price: '53000.00' },
    summary: paidInFull ? SUMMARY : { ...SUMMARY, due_now: '33000.00', outstanding: '33000.00', net_to_pay: '33000.00',
      allocated: '20000.00', course_paid_in_full: false },
    schedule: { final_course_price: '53000.00', standard_course_price: '60000.00', discount_amount: '7000.00',
      month_plan_mode: '', invoiced: '53000.00', projected: '0.00', total: '53000.00', consistent: true, issues: [],
      price_changes: [],
      course: { invoice: 50, number: 'INV-2026-000050', amount: '53000.00', paid: paidInFull ? '53000.00' : '20000.00',
        balance: paidInFull ? '0.00' : '33000.00', status: paidInFull ? 'PAID' : 'PARTIALLY_PAID',
        status_display: paidInFull ? 'Оплачено' : 'Частично оплачено', due_date: '2026-09-01', paid_in_full: paidInFull },
      months: paidInFull ? [1, 2, 3, 4].map((n) => share(n, '13250.00', 'prepaid'))
        : [share(1, '13250.00', 'prepaid'), share(2, '6750.00', 'course_due'), share(3, '0.00', 'course_due'), share(4, '0.00', 'course_due')] },
    months: [{ id: 1, number: 1, month_number: 1, status: 'COMPLETED', lessons_total: 12, lessons_used: 12, lessons_remaining: 0,
      final_price: '53000.00', started_on: '2026-09-02', completed_on: '2026-09-13', invoice: null,
      course_share: { invoice: 50, number: 'INV-2026-000050', amount: '13250.00', paid: '13250.00', paid_in_full: true } }],
    invoices: [], payments: [], contacts: [], reservations: [],
  }) as unknown as ContractCard

  const openCard = () => renderWithProviders(
    <Routes>
      <Route path="/finance/students/:profileId" element={<StudentCardPage />} />
      <Route path="/finance/payments/new" element={<p>Форма платежа</p>} />
    </Routes>, { route: '/finance/students/7' })

  beforeEach(() => {
    vi.mocked(financeApi.lessonBreakdown).mockResolvedValue({ attended: 0, marked: 0, counted: 0, priority_subject: 'IT',
      contract_start: '2026-09-01', totals: {}, priority_before_contract: { count: 0, first_date: null }, lessons: [] })
  })

  it('paid course: debt 0, «Курс полностью оплачен», months are course shares, button stays and opens the form', async () => {
    vi.mocked(financeApi.card).mockResolvedValue(prepaidCard())
    const user = userEvent.setup()
    openCard()
    expect(await screen.findByTestId('course-paid')).toHaveTextContent('Курс полностью оплачен')
    expect(screen.getByTestId('course-paid')).toHaveTextContent(/53\s000/)
    expect(screen.getByTestId('course-prepayment')).toHaveTextContent('курс полностью оплачен')
    const schedule = screen.getByRole('table', { name: 'График оплаты' })
    expect(within(schedule).getAllByRole('row')).toHaveLength(5)
    expect(within(schedule).getAllByText('оплачен предоплатой курса')).toHaveLength(4)
    expect(schedule).not.toHaveTextContent(/53\s000/)  // «Весь курс» — не стоимость месяца №1
    expect(screen.getByText('оплачен предоплатой курса', { selector: 'span.block' })).toBeInTheDocument()
    const add = await screen.findByRole('button', { name: 'Добавить платёж' })  // после загрузки прав
    await user.click(add)
    expect(await screen.findByText('Форма платежа')).toBeInTheDocument()
  })

  it('button is shown for partial prepayment and monthly contracts too', async () => {
    vi.mocked(financeApi.card).mockResolvedValue(prepaidCard(false))
    const { unmount } = openCard()
    expect(await screen.findByRole('button', { name: 'Добавить платёж' })).toBeInTheDocument()
    expect(screen.queryByTestId('course-paid')).not.toBeInTheDocument()
    expect(screen.getAllByText('ждёт оплаты «Весь курс»')).toHaveLength(3)
    unmount()
    vi.mocked(financeApi.card).mockResolvedValue({ ...prepaidCard(), schedule: null, months: [],
      contract: { ...prepaidCard().contract, payment_mode: 'MONTHLY', payment_mode_display: 'Помесячно' },
      summary: { ...SUMMARY, course_paid_in_full: false, due_now: '15000.00' } } as unknown as ContractCard)
    openCard()
    expect(await screen.findByRole('button', { name: 'Добавить платёж' })).toBeInTheDocument()
  })

  it('users who cannot take payments do not see the button', async () => {
    vi.mocked(financeApi.me).mockResolvedValue(DIRECTOR)
    vi.mocked(financeApi.card).mockResolvedValue(prepaidCard())
    openCard()
    expect(await screen.findByTestId('course-paid')).toBeInTheDocument()
    await waitFor(() => expect(financeApi.me).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Добавить платёж' })).not.toBeInTheDocument()
  })
})

describe('План стоимости месяцев', () => {
  it('new contract sends individual month prices; standard is their sum', async () => {
    vi.mocked(financeApi.plans).mockResolvedValue({ count: 1, next: null, previous: null, results: [{
      id: 1, name: "Kid's Club Standard", subject: 1, subject_name: 'IT', course: 1, course_name: "Kid's Club",
      duration_months: 4, payment_deadline_lessons: 3, allow_monthly: true, allow_full_prepay: true, absence_policy: 'ALL_HELD',
      is_active: true, current: { lessons_per_package: 12, package_price: '15000.00', effective_from: '2026-01-01', standard_course_price: '60000.00' },
    }] })
    vi.mocked(financeApi.lmsStudents).mockResolvedValue({ count: 1, next: null, previous: null, results: [
      { id: 3, name: 'Асанов Айбек', group: 1, group_name: 'KC-1', status: 'active', status_display: 'Активен', parent_phone: '', profiles: [] },
    ] })
    vi.mocked(financeApi.createContract).mockResolvedValue({ id: 9 } as never)
    const user = userEvent.setup()
    renderWithProviders(<NewContractPage />, { route: '/finance/contracts/new?student=3' })
    await screen.findByRole('option', { name: "Kid's Club Standard" })
    await user.selectOptions(screen.getByLabelText(/Программа/), '1')
    await user.click(screen.getByLabelText('Индивидуальная стоимость учебных месяцев'))
    const first = screen.getByLabelText('Месяц №1')
    await user.clear(first)
    await user.type(first, '13000')
    expect(screen.getByLabelText('Стандартная стоимость курса')).toHaveValue('58\u00a0000\u00a0сом')
    await user.click(screen.getByLabelText('Скидка предоставлена'))
    await user.type(screen.getByLabelText('Итоговая стоимость курса'), '50000')
    await user.type(screen.getByLabelText(/Причина скидки/), 'Семья')
    await user.click(screen.getByRole('button', { name: /Оформить договор/ }))
    await waitFor(() => expect(financeApi.createContract).toHaveBeenCalled())
    expect(vi.mocked(financeApi.createContract).mock.calls[0][0]).toMatchObject({
      month_prices: ['13000', '15000.00', '15000.00', '15000.00'], month_plan_mode: 'PROPORTIONAL', final_course_price: '50000',
    })
  })

  it('previews and saves the month plan with the chosen distribution rule', async () => {
    vi.mocked(financeApi.saveMonthPlan).mockResolvedValue({ mode: 'PROPORTIONAL', standard_total: '58000.00',
      final_course_price: '50000.00', discount: '8000.00', total: '50000.00', changed: false,
      rows: [{ month_number: 1, standard_price: '13000.00', amount: '11206.90', issued: true },
        { month_number: 2, standard_price: '15000.00', amount: '12931.04', issued: false },
        { month_number: 3, standard_price: '15000.00', amount: '12931.03', issued: false },
        { month_number: 4, standard_price: '15000.00', amount: '12931.03', issued: false }] })
    const month = (n: number, state: 'invoiced' | 'future', amount: string) => ({ month_number: n, state, amount, paid: '0.00',
      balance: state === 'invoiced' ? amount : '0.00', covered_by_credit: '0.00', to_pay: amount, standard_price: n === 1 ? '13000.00' : '15000.00',
      plan_amount: amount, status: state === 'invoiced' ? 'OPEN' as const : undefined, status_display: 'Ожидает оплаты', due_lesson: 3, lessons_used: 1,
      number: state === 'invoiced' ? 'INV-1' : undefined, invoice: state === 'invoiced' ? 1 : undefined })
    const schedule = { month_plan_mode: 'PROPORTIONAL' as const, standard_course_price: '58000.00', discount_amount: '8000.00',
      final_course_price: '50000.00', invoiced: '11206.90', projected: '38793.10', total: '50000.00', consistent: true, issues: [],
      price_changes: [], months: [month(1, 'invoiced', '11206.90'), month(2, 'future', '12931.04'), month(3, 'future', '12931.03'), month(4, 'future', '12931.03')] }
    const user = userEvent.setup()
    renderWithProviders(<ScheduleBlock schedule={schedule} profile={7} canEdit />)
    const table = screen.getByRole('table', { name: 'График оплаты' })
    expect(table).toHaveTextContent('Стандарт')
    expect(table).toHaveTextContent('3-й урок (сейчас 1)')
    expect(screen.getByText(/Стандартная 58\s000/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'План стоимости месяцев' }))
    await user.click(screen.getByRole('button', { name: 'Предпросмотр' }))
    expect(financeApi.saveMonthPlan).toHaveBeenCalledWith(7, expect.objectContaining({ dry_run: true, mode: 'PROPORTIONAL',
      standard_prices: ['13000.00', '15000.00', '15000.00', '15000.00'], final_course_price: '50000.00' }))
    expect(await screen.findByText(/Сумма плана 50\s000/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled()  // без причины
  })
})

describe('Цепочка исправления платежа', () => {
  it('shows the reversed payment as not counted and links replacements both ways', () => {
    const base = { ...PAYMENT, method_display: 'Наличные', receipt: null, allocations: [] }
    const rows = [
      { ...base, id: 42, amount: '19000.00', replaces: [39], replaced_by: [] },
      { ...base, id: 41, amount: '19000.00', replaces: [39], replaced_by: [],
        allocations: [{ id: 1, invoice: 112, invoice_number: 'INV-2026-000112', invoice_period_date: '2026-09-01', amount: '9500.00', status: 'ACTIVE' }] },
      { ...base, id: 39, amount: '38000.00', status: 'void', replaces: [], replaced_by: [41, 42] },
    ] as unknown as Payment[]
    renderWithProviders(<OperationsTable payments={rows} canPay onReverse={() => undefined} />)
    const table = screen.getByRole('table', { name: 'Платежи и чеки' })
    const [, r42, r41, r39] = within(table).getAllByRole('row')
    expect(r39).toHaveTextContent('заменён платежами №41, №42')
    expect(r39).toHaveTextContent('Сторно')
    expect(within(r39).queryByRole('button', { name: 'Сторно' })).not.toBeInTheDocument()  // повторно нельзя
    expect(r41).toHaveTextContent('на INV-2026-000112 · взамен сторнированного №39')
    expect(r42).toHaveTextContent('аванс · взамен сторнированного №39')
  })
})

describe('PrepaymentsPage', () => {
  it('shows totals, statuses and filters by status', async () => {
    const row = { profile: 7, student: 3, student_name: 'Асанов Айбек', program: "Kid's Club", program_id: 1, group: 'KC-1', group_id: 1,
      contract_total: '60000.00', received: '60000.00', applied_to_studied: '30000.00', allocated_future: '30000.00',
      allocated_future_exact: false, unallocated: '0.00', reservation_held: '0.00', prepayment: '30000.00',
      remaining_obligations: '30000.00', paid_months: 4, duration_months: 4, next_covered_month: null, status: 'full' as const,
      status_display: 'Полная предоплата', review_reasons: [] }
    vi.mocked(financeApi.prepayments).mockResolvedValue({
      summary: { prepayment: '55000.00', students: 2, full: 1, partial: 1, advance: 0, review: 0, allocated_future: '30000.00',
        unallocated: '25000.00', reservation_held: '0.00', definitions: { prepayment: 'Деньги заранее', full: 'хватает', partial: 'не хватает',
          allocated_future: 'на будущие', unallocated: 'свободный аванс' } },
      results: [row, { ...row, profile: 8, student_name: 'Бекова Айжан', status: 'partial', status_display: 'Частичная предоплата',
        prepayment: '25000.00', allocated_future: '0.00', unallocated: '25000.00', paid_months: 1, next_covered_month: 2 }],
    })
    const user = userEvent.setup()
    renderWithProviders(<PrepaymentsPage />)
    expect(await screen.findByText('Общий остаток предоплаты')).toBeInTheDocument()
    expect(screen.getAllByText(/55\s000/).length).toBeGreaterThan(0)
    const table = screen.getAllByRole('table')[0]
    expect(table).toHaveTextContent('Остаток предоплаты')
    expect(table).toHaveTextContent('Полная предоплата')
    expect(table).toHaveTextContent('Частичная предоплата')
    expect(table).toHaveTextContent('4 из 4')
    expect(table).toHaveTextContent('№2')
    await user.selectOptions(screen.getByLabelText('Статус'), 'partial')
    await waitFor(() => expect(financeApi.prepayments).toHaveBeenLastCalledWith({ status: 'partial' }))
  })
})
