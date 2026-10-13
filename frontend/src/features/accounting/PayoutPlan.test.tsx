import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PayoutPlanDetailPage } from '@/features/accounting/PayoutPlanDetailPage'
import { PayoutPlanPage } from '@/features/accounting/PayoutPlanPage'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, PayoutPlan, PayoutPlanDetail, PayoutPlanLine } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  newIdempotencyKey: () => 'key-1',
  accountingApi: {
    options: vi.fn(),
    payoutPlans: vi.fn(),
    payoutSummary: vi.fn(),
    payoutCalendar: vi.fn(),
    payoutCandidates: vi.fn(),
    payoutPlan: vi.fn(),
    createPayoutPlan: vi.fn(),
    approvePayoutPlan: vi.fn(),
    cancelPayoutPlan: vi.fn(),
    payPlanLine: vi.fn(),
    updatePayoutLine: vi.fn(),
    updatePayoutPlan: vi.fn(),
    addPayoutLines: vi.fn(),
    downloadPayoutPlan: vi.fn(),
  },
}))

import { accountingApi } from '@/api/accounting'

const OPTIONS = {
  can_view: true, can_operate: true, can_approve: false, employees: [{ id: 9, full_name: 'Айбек Оклад', role: 'assistant' }],
  courses: [], groups: [], salary_types: [], rule_types: [], methods: { FIXED: [], PERCENT: [] }, student_count_rules: [],
  payment_methods: [{ value: 'bank', label: 'Банк' }, { value: 'cash', label: 'Наличные' }], student_payment_methods: [],
  adjustment_kinds: [], payroll_statuses: [], departments: [{ value: 'IT', label: 'IT' }],
} as unknown as AccountingOptions

const TOTALS = {
  planned: '1000000.00', paid: '0.00', remaining: '1000000.00', prepared: '700000.00', deficit: '300000.00',
  readiness_percent: '70.0', employees: 4, status: 'PARTIALLY_FUNDED' as const, status_display: 'Частично профинансировано',
}

const PLAN: PayoutPlan = {
  id: 5, title: 'Зарплата за сентябрь', year: 2026, month: 9, payout_date: '2026-10-01', prepared_amount: '700000.00',
  comment: '', state: 'APPROVED', cancel_reason: '', version: 3, created_by_name: 'Бухгалтер', created_at: '', updated_at: '',
  approved_by_name: 'Бухгалтер', approved_at: '2026-09-30T10:00:00Z', cancelled_by_name: '', cancelled_at: null, totals: TOTALS,
}

const LINE: PayoutPlanLine = {
  id: 11, payroll: 21, employee: 9, employee_name: 'Айбек Оклад', position: 'Ассистент', department: 'IT', department_display: 'IT',
  subjects: [], salary_type: 'FIXED', salary_type_display: 'Оклад', period_label: 'Сентябрь 2026', year: 2026, month: 9,
  accrued: '250000.00', paid_before: '0.00', planned_amount: '250000.00', paid_by_plan: '0.00', remaining_in_plan: '250000.00',
  due_after_plan: '0.00', payroll_status: 'APPROVED', payroll_status_display: 'Утверждён', planned_payment_date: null,
  basis: [{ description: 'Оклад за месяц', amount: '250000.00' }], comment: '', status: 'PLANNED', status_display: 'Запланировано',
}

function detail(patch: Partial<PayoutPlanDetail> = {}): PayoutPlanDetail {
  return { ...PLAN, lines: [LINE], history: [], ...patch }
}

function renderDetail() {
  return renderWithProviders(
    <Routes><Route path="/accounting/payout-plan/:id" element={<PayoutPlanDetailPage />} /></Routes>,
    { route: '/accounting/payout-plan/5' },
  )
}

describe('PayoutPlanPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(accountingApi.payoutPlans).mockResolvedValue({ count: 1, next: null, previous: null, results: [PLAN] })
    vi.mocked(accountingApi.payoutSummary).mockResolvedValue({
      planned: '1000000.00', to_pay: '1000000.00', prepared: '700000.00', deficit: '300000.00', employees: 4, paid: '0.00',
      remaining_obligations: '1000000.00', plans: 1, readiness_percent: '70.0',
    })
    vi.mocked(accountingApi.payoutCalendar).mockResolvedValue({
      days: [{ date: '2026-10-01', to_pay: '1000000.00', prepared: '700000.00', paid: '0.00', deficit: '300000.00', employees: 4,
        readiness_percent: '70.0', plans: [{ id: 5, title: 'Зарплата за сентябрь', status: 'PARTIALLY_FUNDED', status_display: 'Частично профинансировано' }] }],
      suggestions: [{ date: '2026-10-15', amount: '120000.00', employees: 2, payrolls: 2, rule: 'по правилу выплаты (15-е / 1-е число)' }],
    })
  })

  it('shows summary cards from the API and the plans table', async () => {
    renderWithProviders(<PayoutPlanPage />)
    expect(await screen.findByText('Остаток обязательств')).toBeInTheDocument()
    expect(screen.getAllByText('300 000 сом').length).toBeGreaterThan(0)
    expect(screen.getByText('Остаток обязательств')).toBeInTheDocument()
    const row = screen.getByText('Зарплата за сентябрь').closest('tr')!
    expect(within(row).getByText('01.10.2026')).toBeInTheDocument()
    expect(within(row).getByText('1 000 000 сом')).toBeInTheDocument()
    expect(within(row).getByText('Частично профинансировано')).toBeInTheDocument()
  })

  it('passes filters to the backend', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PayoutPlanPage />)
    await screen.findByText('Зарплата за сентябрь')
    await user.selectOptions(screen.getByLabelText('Статус плана'), 'READY')
    await waitFor(() => expect(accountingApi.payoutPlans).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'READY' })))
    expect(accountingApi.payoutSummary).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'READY' }))
  })

  it('shows the calendar with recommended dates', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PayoutPlanPage />)
    await user.click(await screen.findByRole('tab', { name: 'Календарь выплат' }))
    expect(await screen.findByText('Хронология выплат')).toBeInTheDocument()
    expect(screen.getByText('15.10.2026')).toBeInTheDocument()
    expect(screen.getByText('по правилу выплаты (15-е / 1-е число)')).toBeInTheDocument()
  })

  it('hides the create button for read-only users', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue({ ...OPTIONS, can_operate: false })
    renderWithProviders(<PayoutPlanPage />)
    await screen.findByText('Зарплата за сентябрь')
    expect(screen.queryByRole('button', { name: 'Создать план' })).not.toBeInTheDocument()
  })
})

describe('PayoutPlanDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
  })

  it('registers a payment for a line with an idempotency key and blocks overpayment', async () => {
    vi.mocked(accountingApi.payoutPlan).mockResolvedValue(detail())
    vi.mocked(accountingApi.payPlanLine).mockResolvedValue({} as never)
    const user = userEvent.setup()
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Выплатить' }))
    const amount = screen.getByLabelText(/Сумма, сом/)
    await user.clear(amount)
    await user.type(amount, '250000.01')
    expect(screen.getByText('Больше остатка по плану')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Зарегистрировать выплату' })).toBeDisabled()
    await user.clear(amount)
    await user.type(amount, '100000')
    await user.click(screen.getByRole('button', { name: 'Зарегистрировать выплату' }))
    await waitFor(() => expect(accountingApi.payPlanLine).toHaveBeenCalledWith(
      5, 11, expect.objectContaining({ amount: '100000', payment_method: 'bank' }), 'key-1'))
  })

  it('approves a draft with its version', async () => {
    vi.mocked(accountingApi.payoutPlan).mockResolvedValue(detail({ state: 'DRAFT', totals: { ...TOTALS, status: 'DRAFT', status_display: 'Черновик' } }))
    vi.mocked(accountingApi.approvePayoutPlan).mockResolvedValue(detail())
    const user = userEvent.setup()
    renderDetail()
    expect(await screen.findByRole('button', { name: 'Исключить' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Выплатить' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Утвердить' }))
    await waitFor(() => expect(accountingApi.approvePayoutPlan).toHaveBeenCalledWith(5, 3))
  })

  it('cancels only with a reason', async () => {
    vi.mocked(accountingApi.payoutPlan).mockResolvedValue(detail())
    vi.mocked(accountingApi.cancelPayoutPlan).mockResolvedValue(detail({ state: 'CANCELLED' }))
    const user = userEvent.setup()
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Отменить план' }))
    const dialog = screen.getByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Отменить план' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByLabelText(/Причина/), 'перенос на 15-е')
    await user.click(confirm)
    await waitFor(() => expect(accountingApi.cancelPayoutPlan).toHaveBeenCalledWith(5, 3, 'перенос на 15-е'))
  })

  it('explains why the amount was planned', async () => {
    vi.mocked(accountingApi.payoutPlan).mockResolvedValue(detail())
    const user = userEvent.setup()
    renderDetail()
    await user.click(await screen.findByRole('button', { name: 'Почему такая сумма' }))
    expect(screen.getByText('Оклад за месяц: 250 000 сом')).toBeInTheDocument()
  })

  it('director sees the plan without action buttons', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue({ ...OPTIONS, can_operate: false })
    vi.mocked(accountingApi.payoutPlan).mockResolvedValue(detail())
    renderDetail()
    expect(await screen.findByText('Айбек Оклад')).toBeInTheDocument()
    for (const name of ['Выплатить', 'Отменить план', 'Изменить', 'Утвердить']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Excel' })).toBeInTheDocument()
  })
})
