import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AccountingDashboardPage } from '@/features/accounting/DashboardPage'
import { som } from '@/features/accounting/shared'
import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, Dashboard } from '@/types/accounting'
import type { UserRole } from '@/types/auth'

const mockRole = vi.hoisted(() => ({ role: 'accountant' as UserRole }))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: mockRole.role }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/accounting', () => ({
  periodParams: vi.fn(),
  newIdempotencyKey: () => 'key',
  accountingApi: {
    options: vi.fn(),
    dashboard: vi.fn(),
    employees: vi.fn(),
    ensurePeriod: vi.fn(),
    calculatePeriod: vi.fn(),
    approvePeriod: vi.fn(),
    downloadReport: vi.fn(),
  },
}))

import { accountingApi } from '@/api/accounting'

const OPTIONS = {
  employees: [], courses: [], groups: [], salary_types: [], rule_types: [], methods: {}, revenue_bases: [],
  refund_policies: [], payment_methods: [], student_payment_methods: [], adjustment_kinds: [], payroll_statuses: [],
  can_view: true, can_operate: true, can_approve: false,
} as unknown as AccountingOptions

const PERIOD = {
  id: 4, year: 2026, month: 9, period_type: 'FIRST_HALF' as const, period_type_display: '1–15', start_date: '2026-09-01',
  end_date: '2026-09-15', status: 'CALCULATED' as const, status_display: 'Рассчитан', label: '01.09.2026–15.09.2026',
  created_at: '', approved_at: null,
}

const DASHBOARD: Dashboard = {
  total_accrued: '16500.00', total_lines: '16500.00', total_adjustments: '0.00', total_paid: '6500.00',
  total_due: '10000.00', employees_with_accruals: 1, pending_approval: 1, pending_adjustments: 0, with_errors: 0,
  outstanding_debt_all_periods: '10000.00', range_label: '01.09.2026–15.09.2026', periods: [PERIOD],
}

describe('som', () => {
  it('formats Decimal strings without float rounding', () => {
    expect(som('16500.00')).toBe('16 500 сом')
    expect(som('1234567.5')).toBe('1 234 567,50 сом')
    expect(som('-400.00')).toBe('−400 сом')
    expect(som(null)).toBe('—')
  })
})

describe('AccountingDashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.role = 'accountant'
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(accountingApi.dashboard).mockResolvedValue(DASHBOARD)
    vi.mocked(accountingApi.employees).mockResolvedValue({
      range_label: DASHBOARD.range_label,
      results: [{
        profile_id: 1, employee: 9, employee_name: 'Islam Test', position: 'Программист', salary_type: 'PER_STUDENT',
        salary_type_display: 'За активного студента', is_active: true,
        rates: [{ rule_type: 'PER_STUDENT', label: 'За активного студента', amount: '11000.00', percentage: null, scope: '' }],
        active_students: 3, payroll_id: 12, accrued: '16500.00', paid: '6500.00', due: '10000.00',
        status: 'PARTIALLY_PAID', status_display: 'Частично выплачен',
      }],
    })
    vi.mocked(accountingApi.ensurePeriod).mockResolvedValue(PERIOD)
    vi.mocked(accountingApi.calculatePeriod).mockResolvedValue({
      period: PERIOD,
      calculated: [],
      skipped: [],
      failed: [{ employee_id: 3, employee: 'Без ставки', error: 'Не настроена ставка' }],
    })
  })

  it('shows totals, employees and runs the mass calculation with its errors', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AccountingDashboardPage />, { route: '/accounting?year=2026&month=9&half=FIRST_HALF' })

    await waitFor(() => expect(screen.getByText('Islam Test')).toBeInTheDocument())
    expect(screen.getAllByText(/16\s500\sсом/).length).toBeGreaterThan(0)
    expect(screen.getByText('Частично выплачен')).toBeInTheDocument()
    // Бухгалтер не утверждает — кнопки утверждения нет.
    expect(screen.queryByText('Утвердить все без ошибок')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Рассчитать зарплаты' }))
    await waitFor(() => expect(accountingApi.calculatePeriod).toHaveBeenCalledWith(4))
    expect(accountingApi.ensurePeriod).toHaveBeenCalledWith(2026, 9, 'FIRST_HALF')
    expect(await screen.findByText(/Без ставки: Не настроена ставка/)).toBeInTheDocument()
  })

  it('offers approval to the director only', async () => {
    mockRole.role = 'director'
    vi.mocked(accountingApi.options).mockResolvedValue({ ...OPTIONS, can_operate: false, can_approve: true })
    renderWithProviders(<AccountingDashboardPage />, { route: '/accounting?year=2026&month=9&half=FIRST_HALF' })
    expect(await screen.findByRole('button', { name: 'Утвердить все без ошибок' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Рассчитать зарплаты' })).not.toBeInTheDocument()
  })
})
