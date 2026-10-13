import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EarningsPage } from '@/features/accounting/EarningsPage'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, Earnings, EarningsRow } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: { options: vi.fn(), earnings: vi.fn(), employeeEarnings: vi.fn() },
}))

import { accountingApi } from '@/api/accounting'

const AMOUNTS = {
  earned: { gross: '17500.00', tax: '1000.00', other_deductions: '0.00', net: '16500.00' },
  official: { gross: '10000.00', tax: '1000.00', other_deductions: '0.00', net: '9000.00' },
  paid: '2000.00', company_owes: '7000.00', earned_unpaid: '14500.00', next_payment_date: '2026-10-15', difference: '7500.00',
  difference_reasons: [{ source: 'OPEN_BLOCK' as const, label: 'Блок идёт — официальное начисление после завершения блока', amount: '7500.00' }],
}
const ROW: EarningsRow = {
  employee: 7, employee_name: 'Тренер Айтиев', position: 'Тренер', salary_type: 'PERCENT',
  salary_type_display: 'Процент от стоимости курса', department: 'IT', ...AMOUNTS,
}
const DETAIL: Earnings & { employee: number; employee_name: string } = {
  ...AMOUNTS, employee: 7, employee_name: 'Тренер Айтиев', as_of: '2026-10-10', deductions: [],
  items: [{
    source: 'OPEN_BLOCK', source_display: '', official: false, year: 2026, month: 10, period_label: 'Октябрь 2026', gross: '7500.00',
    planned_payment_date: null, payroll_id: null, cycle_id: 3, cycle_number: 2, group_name: 'Group A', course_name: 'Prog SOFT',
    subject_name: 'Python', lessons_taught: 9, lessons_done: 9, required_lessons: 12, formula: '10 студ. × 10000 сом × 10% × 9/12 ур.',
  }, {
    source: 'PAYROLL_OFFICIAL', source_display: '', official: true, year: 2026, month: 10, period_label: '01.10.2026–15.10.2026',
    gross: '10000.00', planned_payment_date: '2026-10-15', payroll_id: 5, payroll_status_display: 'Частично выплачен',
    lines: [{ description: 'Python, блок 1', amount: '10000.00' }],
  }],
}

describe('EarningsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountingApi.options).mockResolvedValue({ departments: [] } as unknown as AccountingOptions)
    vi.mocked(accountingApi.earnings).mockResolvedValue({ count: 1, next: null, previous: null, results: [ROW] })
    vi.mocked(accountingApi.employeeEarnings).mockResolvedValue(DETAIL)
  })

  it('shows earned, deductions, net, official, paid and obligations per employee', async () => {
    renderWithProviders(<EarningsPage />)
    const row = (await screen.findByText('Тренер Айтиев')).closest('tr')!
    for (const value of ['17 500 сом', '1 000 сом', '16 500 сом', '10 000 сом', '2 000 сом', '7 000 сом', '15.10.2026']) {
      expect(row).toHaveTextContent(value)
    }
    expect(row).toHaveTextContent('вне начисления 7 500 сом')
  })

  it('expands details by subject, group and block with the reason for the difference', async () => {
    const user = userEvent.setup()
    renderWithProviders(<EarningsPage />)
    await user.click(await screen.findByText('Тренер Айтиев'))
    await waitFor(() => expect(accountingApi.employeeEarnings).toHaveBeenCalledWith(7))
    expect(await screen.findByText('9 из 12 уроков проведено вами')).toBeInTheDocument()
    expect(screen.getByText(/Python · Group A/)).toBeInTheDocument()
    expect(screen.getByText(/Блок идёт — официальное начисление после завершения блока: 7 500 сом/)).toBeInTheDocument()
    expect(screen.getAllByText('Начислено официально').length).toBe(2) // колонка + статус строки
  })
})
