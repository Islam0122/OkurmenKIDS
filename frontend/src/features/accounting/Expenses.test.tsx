import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ACCOUNTING_NAV, ACCOUNTING_SECTIONS } from '@/features/accounting/AccountingLayout'
import { CashFlowPage } from '@/features/accounting/CashFlowPage'
import { ExpensesPage } from '@/features/accounting/ExpensesPage'
import { FinancePanelPage } from '@/features/accounting/FinancePanelPage'
import { AccountingHomePage } from '@/features/accounting/HomePage'
import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, Expense, ExpenseOptions, FinanceOverview } from '@/types/accounting'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: 'accountant' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/finance', () => ({
  financeApi: { me: vi.fn(), counts: vi.fn() },
}))
vi.mock('@/api/accounting', () => ({
  newIdempotencyKey: () => 'key-1',
  accountingApi: {
    options: vi.fn(),
    expenseOptions: vi.fn(),
    expenses: vi.fn(),
    expense: vi.fn(),
    expenseHistory: vi.fn(),
    createExpense: vi.fn(),
    payExpense: vi.fn(),
    financeOverview: vi.fn(),
    cashFlow: vi.fn(),
    downloadFinanceReport: vi.fn(),
  },
}))

import { accountingApi } from '@/api/accounting'
import { financeApi } from '@/api/finance'

const OPTIONS = { can_view: true, can_operate: true, can_approve: false } as unknown as AccountingOptions

const EXPENSE_OPTIONS: ExpenseOptions = {
  categories: [
    { id: 1, code: 'rent', name: 'Аренда офиса и учебных помещений', description: '', sort_order: 10, is_active: true, expenses_count: 1 },
    { id: 2, code: 'old', name: 'Старая категория', description: '', sort_order: 20, is_active: false, expenses_count: 0 },
  ],
  payment_methods: [{ value: 'cash', label: 'Наличные' }, { value: 'bank', label: 'Банковский перевод' }],
  statuses: [{ value: 'UNPAID', label: 'Не оплачен' }, { value: 'PAID', label: 'Оплачен' }, { value: 'VOID', label: 'Отменён' }],
  staff: [{ id: 5, name: 'Test Buh' }],
  unpaid: { amount: '50000.00', count: 1, overdue_amount: '0.00', overdue_count: 0 },
}

const EXPENSE: Expense = {
  id: 7, category: 1, category_name: 'Аренда офиса и учебных помещений', description: 'Аренда октябрь', amount: '50000.00',
  currency: 'KGS', expense_date: '2026-10-01', due_date: '2026-10-05', vendor: 'Арендодатель', payment_method: 'bank',
  payment_method_display: 'Банковский перевод', responsible: null, responsible_name: '', reference: 'INV-7', comment: '',
  status: 'UNPAID', status_display: 'Не оплачен', paid_date: null, is_overdue: false, has_document: false, document_name: '',
  recurring: null, recurring_description: null, recurrence_month: null, void_reason: '', version: 3, created_by: 1,
  created_by_name: 'Test Buh', created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z', voided_by: null,
  voided_by_name: '', voided_at: null,
}

const change = (current: string, previous: string, delta: string, percent: string | null) => ({ current, previous, delta, percent })

const OVERVIEW: FinanceOverview = {
  date_from: '2026-10-01', date_to: '2026-10-31', previous_period: { date_from: '2026-09-01', date_to: '2026-09-30' },
  branches_supported: false,
  students: {
    gross: '30000.00', count: 2, refunds: '2000.00', refunds_count: 1, net: '28000.00', invoiced: '45000.00', invoiced_count: 3,
    expected: '40000.00', expected_paid: '28000.00', debt_end: '12000.00', debt_now: '17000.00', overdue_now: '5000.00',
    overdue_students: 1, students_awaiting: 2, prepayment: '9000.00', prepayment_students: 1, unallocated_credit: '1000.00',
    prepayment_review: 0,
  },
  payroll: {
    accrued: '20000.00', deductions: '0.00', paid_on_accrued: '5000.00', outstanding_on_accrued: '15000.00',
    awaiting_approval: '0.00', employees: 2, paid_cash: '8000.00', paid_cash_count: 2, outstanding_now: '15000.00',
  },
  expenses: {
    paid: '10000.00', incurred: '60000.00', unpaid_now_amount: '50000.00', unpaid_now_count: 1,
    unpaid_now_overdue_amount: '0.00', unpaid_now_overdue_count: 0,
  },
  cash_flow: {
    inflow: '30000.00', outflow: '20000.00', net: '10000.00', outflow_refunds: '2000.00', outflow_payroll: '8000.00',
    outflow_expenses: '10000.00',
    by_method: [{ method: 'cash', method_display: 'Наличные', inflow: '30000.00', outflow: '20000.00', net: '10000.00' }],
  },
  result: { cash: '10000.00', cash_basis: 'Денежный результат = поступления − выплаты.', accrual: null, accrual_note: 'Результат по методу начисления не рассчитывается.' },
  comparison: {
    student_receipts: change('28000.00', '20000.00', '8000.00', '40.0'),
    payroll_accrued: change('20000.00', '20000.00', '0.00', '0.0'),
    payroll_paid: change('8000.00', '6000.00', '2000.00', '33.3'),
    expenses_paid: change('10000.00', '5000.00', '5000.00', '100.0'),
    cash_flow_net: change('10000.00', '9000.00', '1000.00', '11.1'),
  },
  history: [{ year: 2026, month: 10, inflow: '30000.00', refunds: '2000.00', payroll: '8000.00', expenses: '10000.00', outflow: '20000.00', net: '10000.00' }],
  definitions: {},
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
  vi.mocked(accountingApi.expenseOptions).mockResolvedValue(EXPENSE_OPTIONS)
  vi.mocked(accountingApi.expenses).mockResolvedValue({
    count: 1, next: null, previous: null, results: [EXPENSE], totals: { total: '50000.00', paid: '0.00', unpaid: '50000.00' },
  })
  vi.mocked(accountingApi.expense).mockResolvedValue(EXPENSE)
  vi.mocked(accountingApi.expenseHistory).mockResolvedValue({ results: [] })
  vi.mocked(accountingApi.financeOverview).mockResolvedValue(OVERVIEW)
  vi.mocked(financeApi.me).mockResolvedValue({ can_view_money: true } as never)
  vi.mocked(financeApi.counts).mockResolvedValue({ to_pay: 4, soon: 3, overdue: 2 })
})

describe('Навигация бухгалтерии', () => {
  it('groups the menu into the four main sections plus cash and settings', () => {
    const titles = ACCOUNTING_SECTIONS.map((s) => s.title).filter(Boolean)
    expect(titles).toEqual(['Оплата студентов', 'Зарплата сотрудников', 'Расходы компании', 'Аналитика и касса', 'Финансовые настройки'])
    const paths = ACCOUNTING_NAV.map((i) => i.to)
    expect(new Set(paths).size).toBe(paths.length)
    expect(paths).toEqual(expect.arrayContaining(['/accounting', '/accounting/payroll', '/accounting/expenses', '/accounting/finance', '/accounting/cash']))
  })
})

describe('AccountingHomePage', () => {
  it('shows every section with its sub-sections and queue counters', async () => {
    renderWithProviders(<AccountingHomePage />, { route: '/accounting' })
    for (const title of ['1. Оплата студентов', '2. Зарплата сотрудников', '3. Расходы компании', '4. Аналитика и отчёты', 'Касса и движение денег', 'Финансовые настройки']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: /Полностью оплаченные курсы/ })).toHaveAttribute('href', '/finance/soon?section=paid_course')
    expect(screen.getByRole('link', { name: /^Возвраты/ })).toHaveAttribute('href', '/finance/payments?kind=refund')
    const overdue = await screen.findByRole('link', { name: /Просроченные платежи/ })
    await waitFor(() => expect(within(overdue).getByText('2')).toBeInTheDocument())
    expect(await screen.findAllByText(/17\s000\sсом/)).not.toHaveLength(0)
  })
})

describe('FinancePanelPage', () => {
  it('keeps receipts, invoices, prepayments, payroll and expenses apart and explains the result', async () => {
    renderWithProviders(<FinancePanelPage />)
    expect(await screen.findByText('Денежный результат')).toBeInTheDocument()
    expect(screen.getByText('Выставлено начислений')).toBeInTheDocument()
    expect(screen.getByText(/не доход и не деньги/)).toBeInTheDocument()
    expect(screen.getByText('Остатки авансов')).toBeInTheDocument()
    expect(screen.getByText('Результат по методу начисления не рассчитывается.')).toBeInTheDocument()
    expect(accountingApi.financeOverview).toHaveBeenCalledWith({ month: expect.stringMatching(/^\d{4}-\d{2}$/) })
    // Рост расходов — не «хорошо»: бейдж красный.
    const row = screen.getByText('Оплаченные расходы').closest('tr') as HTMLElement
    expect(within(row).getByText(/\+5\s000\sсом/).className).toMatch(/danger/)
  })
})

describe('CashFlowPage', () => {
  it('lists money movements with direction and totals', async () => {
    vi.mocked(accountingApi.cashFlow).mockResolvedValue({
      count: 1, next: null, previous: null, date_from: '2026-10-01', date_to: '2026-10-31', note: 'Остаток кассы на начало периода не ведётся.',
      summary: { inflow: '0.00', outflow: '50000.00', net: '-50000.00', count: 1, by_method: [] },
      results: [{
        key: 'ex-7', date: '2026-10-05', kind: 'expense', kind_display: 'Оплата расхода', direction: 'out', amount: '50000.00',
        method: 'bank', method_display: 'Банковский перевод', counterparty: 'Арендодатель', description: 'Аренда: октябрь',
        reference: 'INV-7', source_id: 7, link: '/accounting/expenses?expense=7',
      }],
    })
    renderWithProviders(<CashFlowPage />)
    expect(await screen.findByRole('link', { name: 'Арендодатель' })).toHaveAttribute('href', '/accounting/expenses?expense=7')
    expect(screen.getByText(/−50\s000\sсом/, { selector: 'td' })).toBeInTheDocument()
  })
})

describe('ExpensesPage', () => {
  it('creates an unpaid expense by default with an idempotency key', async () => {
    const user = userEvent.setup()
    vi.mocked(accountingApi.createExpense).mockResolvedValue(EXPENSE)
    renderWithProviders(<ExpensesPage />, { route: '/accounting/expenses' })
    await user.click(await screen.findByRole('button', { name: 'Добавить расход' }))
    const dialog = await screen.findByRole('dialog')
    // Отключённая категория в новом расходе не предлагается.
    expect(within(dialog).queryByRole('option', { name: 'Старая категория' })).not.toBeInTheDocument()
    await user.selectOptions(within(dialog).getByLabelText(/Категория/), '1')
    await user.type(within(dialog).getByLabelText(/Сумма/), '1500')
    await user.type(within(dialog).getByLabelText(/Описание/), 'Бумага')
    await user.click(within(dialog).getByRole('button', { name: 'Добавить' }))
    await waitFor(() => expect(accountingApi.createExpense).toHaveBeenCalledWith(
      expect.objectContaining({ category: 1, amount: '1500', description: 'Бумага', paid: false, paid_date: null }), 'key-1'))
  })

  it('opens the expense card from the link and registers the payment', async () => {
    const user = userEvent.setup()
    vi.mocked(accountingApi.payExpense).mockResolvedValue({ ...EXPENSE, status: 'PAID' })
    renderWithProviders(<ExpensesPage />, { route: '/accounting/expenses?expense=7' })
    await user.click(await screen.findByRole('button', { name: 'Отметить оплату' }))
    const dialogs = await screen.findAllByRole('dialog')
    await user.click(within(dialogs[dialogs.length - 1]).getByRole('button', { name: 'Отметить оплату' }))
    await waitFor(() => expect(accountingApi.payExpense).toHaveBeenCalledWith(7, expect.objectContaining({ version: 3, payment_method: 'bank', reference: 'INV-7' })))
  })
})
