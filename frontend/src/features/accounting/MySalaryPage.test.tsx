import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MySalaryPage } from '@/features/accounting/MySalaryPage'
import { renderWithProviders } from '@/test/testUtils'
import type { MySalary, MySalaryRow } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: { mySalary: vi.fn(), downloadMySalaryPdf: vi.fn(), myPayoutPlan: vi.fn().mockResolvedValue({ results: [] }) },
}))

import { accountingApi } from '@/api/accounting'

const awaiting = (period_type: 'FIRST_HALF' | 'SECOND_HALF'): MySalaryRow => ({
  payroll_id: null, year: 2026, month: 10, period_type, period_label: '', status: 'AWAITING',
  status_display: 'Ожидает расчёта', is_final: false, accrued: null, paid: null, due: null, lines: [], adjustments: [],
  deducted: null, deductions: [], planned_payment_date: null,
})

const EMPTY: MySalary = {
  employee_name: 'Asya Test',
  has_profile: false,
  profile: null,
  totals: { accrued: '0.00', deducted: '0.00', net: '0.00', paid: '0.00', due: '0.00', pending_approval: '0.00', estimated: '0.00', estimated_deductions: null, estimated_deductions_note: '' },
  deductions: [],
  earnings: {
    as_of: '2026-10-10', earned: { gross: '0.00', tax: '0.00', other_deductions: '0.00', net: '0.00' },
    official: { gross: '0.00', tax: '0.00', other_deductions: '0.00', net: '0.00' }, paid: '0.00', company_owes: '0.00',
    earned_unpaid: '0.00', next_payment_date: null, difference: '0.00', difference_reasons: [], items: [], deductions: [],
  },
  next_planned_payment_date: null,
  estimates: [],
  last_payment: null,
  current_month: { year: 2026, month: 10, label: 'Октябрь 2026', accrued: '0.00', periods: [awaiting('FIRST_HALF'), awaiting('SECOND_HALF')] },
  history: [],
  payments: [],
  filters: { year: null, month: null, period_type: null },
}

const WITH_DATA: MySalary = {
  ...EMPTY,
  has_profile: true,
  profile: {
    salary_type: 'FIXED', salary_type_display: 'Фиксированный оклад', position: 'Ассистент',
    rates: [{ rule_type: 'FIXED', label: 'Оклад', amount: '40000.00', percentage: null, scope: '', effective_from: '2026-01-01' }],
  },
  totals: { accrued: '20000.00', deducted: '0.00', net: '20000.00', paid: '15000.00', due: '5000.00', pending_approval: '20000.00', estimated: '0.00', estimated_deductions: null, estimated_deductions_note: '' },
  last_payment: { payment_date: '2026-09-20', amount: '15000.00' },
  history: [
    {
      ...awaiting('SECOND_HALF'), payroll_id: 2, year: 2026, month: 9, period_label: '16.09.2026–30.09.2026',
      status: 'CALCULATED', status_display: 'Рассчитано, ожидает утверждения', accrued: '20000.00', paid: '0.00', due: '20000.00',
      lines: [{ description: 'Оклад за вторую половину месяца', amount: '20000.00' }],
    },
    {
      ...awaiting('FIRST_HALF'), payroll_id: 1, year: 2026, month: 9, period_label: '01.09.2026–15.09.2026',
      status: 'PARTIALLY_PAID', status_display: 'Частично выплачено', is_final: true, accrued: '20000.00', paid: '15000.00', due: '5000.00',
    },
  ],
  payments: [{ id: 5, payment_date: '2026-09-20', amount: '15000.00', method: 'Банковский перевод', is_advance: false, reference: '', period_label: '01.09.2026–15.09.2026', payroll_id: 1 }],
}

describe('MySalaryPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a clear message instead of an error when there is nothing yet', async () => {
    vi.mocked(accountingApi.mySalary).mockResolvedValue(EMPTY)
    renderWithProviders(<MySalaryPage />)
    expect(await screen.findByText('Начислений пока нет')).toBeInTheDocument()
    expect(screen.getByText('Зарплатный профиль ещё не настроен бухгалтерией.')).toBeInTheDocument()
    expect(screen.getByText('Выплат пока не было.')).toBeInTheDocument()
    expect(screen.getAllByText('Ожидает расчёта')).toHaveLength(2)
  })

  it('shows the four cards, statuses, payments and never sends an employee id', async () => {
    vi.mocked(accountingApi.mySalary).mockResolvedValue(WITH_DATA)
    const user = userEvent.setup()
    renderWithProviders(<MySalaryPage />)
    expect(await screen.findByText('Рассчитано, ожидает утверждения')).toBeInTheDocument()
    for (const label of ['Официально начислено', 'Фактически выплачено', 'Остаток к выплате', 'Ближайшая дата выплаты']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    expect(screen.getByText(/40\s000\sсом в месяц/)).toBeInTheDocument()
    expect(screen.getByText('Частично выплачено')).toBeInTheDocument()
    expect(screen.getByText('Банковский перевод')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Месяц'), '9')
    await waitFor(() => expect(accountingApi.mySalary).toHaveBeenLastCalledWith({ month: 9 }))
    for (const [args] of vi.mocked(accountingApi.mySalary).mock.calls) {
      expect(Object.keys(args ?? {})).not.toContain('employee')
    }
    await user.click(screen.getByRole('button', { name: 'Скачать PDF' }))
    expect(accountingApi.downloadMySalaryPdf).toHaveBeenCalledWith({ month: 9 })
  })

  it('offers a retry when the API fails', async () => {
    vi.mocked(accountingApi.mySalary).mockRejectedValue(new Error('boom'))
    renderWithProviders(<MySalaryPage />)
    expect(await screen.findByRole('button', { name: /повтор/i })).toBeInTheDocument()
  })
})

describe('MySalaryPage — налоги и удержания', () => {
  const TAXED: MySalary = {
    ...WITH_DATA,
    totals: { ...WITH_DATA.totals, accrued: '50000.00', deducted: '3000.00', net: '47000.00', paid: '20000.00', due: '27000.00', pending_approval: '0.00' },
    deductions: [{
      id: 1, name: 'Налог', kind: 'TAX', kind_display: 'Налог', year: 2026, month: 10, period_label: 'Октябрь 2026',
      month_amount: '3000.00', withheld: '3000.00', remaining: '0.00', status: 'WITHHELD', status_display: 'Удержано', applied_at: '2026-11-01',
    }],
    history: [{
      ...awaiting('FIRST_HALF'), payroll_id: 1, year: 2026, month: 10, period_label: '01.10.2026–31.10.2026',
      status: 'PARTIALLY_PAID', status_display: 'Частично выплачено', is_final: true, accrued: '50000.00', paid: '20000.00', due: '27000.00',
      deducted: '3000.00', lines: [{ description: 'Оклад', amount: '50000.00' }],
      deductions: [{ name: 'Налог', kind_display: 'Налог', amount: '3000.00', month_amount: '3000.00', remaining: '0.00' }],
    }],
  }

  it('shows earned, tax, other deductions, net, official, paid and debt from the API', async () => {
    vi.mocked(accountingApi.mySalary).mockResolvedValue({
      ...TAXED,
      earnings: {
        ...EMPTY.earnings,
        earned: { gross: '57500.00', tax: '3000.00', other_deductions: '500.00', net: '54000.00' },
        official: { gross: '50000.00', tax: '3000.00', other_deductions: '500.00', net: '46500.00' },
        paid: '20000.00', company_owes: '26500.00', earned_unpaid: '34000.00', next_payment_date: '2026-11-01',
        difference: '7500.00', difference_reasons: [{ source: 'OPEN_BLOCK', label: 'Блок идёт — официальное начисление после завершения блока', amount: '7500.00' }],
        items: [{
          source: 'OPEN_BLOCK', source_display: '', official: false, year: 2026, month: 10, period_label: 'Октябрь 2026',
          gross: '7500.00', planned_payment_date: null, payroll_id: null, cycle_id: 3, cycle_number: 2, group_name: 'Group A',
          course_name: 'Prog SOFT', subject_name: 'Python', lessons_taught: 9, lessons_done: 9, required_lessons: 12,
          student_count: 10, price_per_student: '10000.00', percentage: '10.00', formula: '10 студ. × 10000 сом × 10% × 9/12 ур.',
        }],
      },
    })
    renderWithProviders(<MySalaryPage />)
    const card = async (label: string) => (await screen.findAllByText(label))[0].closest('[class*="card"]') as HTMLElement
    expect(await card('Заработано на текущий момент')).toHaveTextContent('57 500 сом')
    expect(await card('Налог')).toHaveTextContent('3 000 сом')
    expect(await card('Другие удержания')).toHaveTextContent('500 сом')
    expect(await card('Ожидаемая сумма на руки')).toHaveTextContent('54 000 сом')
    expect(await card('Официально начислено')).toHaveTextContent('50 000 сом')
    expect(await card('Фактически выплачено')).toHaveTextContent('20 000 сом')
    expect(await card('Остаток к выплате')).toHaveTextContent('26 500 сом')
    expect(await card('Ближайшая дата выплаты')).toHaveTextContent('01.11.2026')
    expect(screen.getByText('9 из 12 уроков проведено вами')).toBeInTheDocument()
    expect(screen.getByText(/Блок идёт — официальное начисление после завершения блока: 7 500 сом/)).toBeInTheDocument()
    expect(screen.queryByText(/Предварительная зарплата/)).not.toBeInTheDocument()
    expect(screen.queryByText(/прогноз/i)).not.toBeInTheDocument()
  })

  it('lists own deductions with period, amount, status and date', async () => {
    vi.mocked(accountingApi.mySalary).mockResolvedValue(TAXED)
    const user = userEvent.setup()
    renderWithProviders(<MySalaryPage />)
    const row = (await screen.findByText('Октябрь 2026')).closest('tr')!
    expect(row).toHaveTextContent('Налог')
    expect(row).toHaveTextContent('3 000 сом')
    expect(row).toHaveTextContent('Удержано')
    expect(row).toHaveTextContent('01.11.2026')
    const payroll = screen.getByText('01.10.2026–31.10.2026').closest('tr')!
    await user.click(payroll)
    expect(screen.getByText('−3 000 сом')).toBeInTheDocument()
  })
})
