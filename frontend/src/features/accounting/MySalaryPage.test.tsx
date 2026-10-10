import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MySalaryPage } from '@/features/accounting/MySalaryPage'
import { renderWithProviders } from '@/test/testUtils'
import type { MyEstimate, MySalary, MySalaryRow } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: { mySalary: vi.fn(), downloadMySalaryPdf: vi.fn() },
}))

import { accountingApi } from '@/api/accounting'

const awaiting = (period_type: 'FIRST_HALF' | 'SECOND_HALF'): MySalaryRow => ({
  payroll_id: null, year: 2026, month: 10, period_type, period_label: '', status: 'AWAITING',
  status_display: 'Ожидает расчёта', is_final: false, accrued: null, paid: null, due: null, lines: [], adjustments: [],
  planned_payment_date: null,
})

const EMPTY: MySalary = {
  employee_name: 'Asya Test',
  has_profile: false,
  profile: null,
  totals: { accrued: '0.00', paid: '0.00', due: '0.00', pending_approval: '0.00', estimated: '0.00' },
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
  totals: { accrued: '20000.00', paid: '15000.00', due: '5000.00', pending_approval: '20000.00', estimated: '0.00' },
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
    for (const label of ['Начислено', 'Выплачено', 'Остаток к выплате', 'Последняя выплата']) {
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

  it('shows the preliminary salary of blocks in progress separately from accruals', async () => {
    const block = (done: number, total: number, group: string): MyEstimate => ({
      cycle_id: total, cycle_number: 1, group_name: group, course_name: 'Prog SOFT', subjects: ['Python'], student_count: 10,
      price_per_student: '10000.00', percentage: '10.00', expected_amount: '10000.00', lessons_done: done,
      required_lessons: total, lessons_remaining: total - done, projected_completion_date: '2026-10-19',
      expected_payment_date: '2026-11-01', status: 'BLOCK_IN_PROGRESS', status_display: 'Блок в процессе', warnings: [],
      note: 'Предварительный расчёт — не начисление и не задолженность.',
    })
    vi.mocked(accountingApi.mySalary).mockResolvedValue({
      ...EMPTY, has_profile: true,
      totals: { ...EMPTY.totals, estimated: '20000.00' },
      estimates: [block(8, 12, 'Python A'), block(8, 20, 'Python B')],
    })
    renderWithProviders(<MySalaryPage />)
    expect((await screen.findAllByText('Предварительная зарплата')).length).toBe(3) // карточка KPI + 2 блока
    expect(screen.getByText('8 из 12 уроков')).toBeInTheDocument()
    expect(screen.getByText('8 из 20 уроков')).toBeInTheDocument()
    expect(screen.getByText('Осталось провести: 4')).toBeInTheDocument()
    expect(screen.getByText('Осталось провести: 12')).toBeInTheDocument()
    expect(screen.getAllByText('Блок в процессе')).toHaveLength(2)
    expect(screen.getAllByRole('progressbar')).toHaveLength(2)
    // Оценка не попадает в «Начислено»: там по-прежнему 0.
    expect(screen.getByText(/20\s000\sсом/)).toBeInTheDocument()
    expect(screen.getAllByText(/20\s000\sсом/)).toHaveLength(1)
    expect(screen.getAllByText(/^0\sсом$/).length).toBeGreaterThanOrEqual(3) // начислено, выплачено, остаток
    expect(screen.getAllByText(/ожидаемая выплата 01\.11\.2026/)).toHaveLength(2)
    // Сотруднику не предлагается регистрировать выплату.
    expect(screen.queryByRole('button', { name: /выплат/i })).not.toBeInTheDocument()
  })

  it('offers a retry when the API fails', async () => {
    vi.mocked(accountingApi.mySalary).mockRejectedValue(new Error('boom'))
    renderWithProviders(<MySalaryPage />)
    expect(await screen.findByRole('button', { name: /повтор/i })).toBeInTheDocument()
  })
})
