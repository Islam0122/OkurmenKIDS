import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { MySalary } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: { mySalary: vi.fn(), downloadMySalaryPdf: vi.fn(), myPayoutPlan: vi.fn().mockResolvedValue({ results: [] }) },
}))
vi.mock('@/api/operations', () => ({
  operationsApi: {},
  tasksApi: {},
  notificationsApi: { unreadCount: vi.fn().mockResolvedValue({ count: 0 }), list: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }) },
  workReportsApi: {},
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 7, role: 'operations_director', first_name: 'Олег', last_name: 'Директоров' }, status: 'authenticated', logout: vi.fn() }),
}))

import { accountingApi } from '@/api/accounting'
import { MySalaryRedirect } from '@/app/router/MySalaryRedirect'
import { MySalaryPage } from '@/features/accounting/MySalaryPage'

import { OperationsLayout } from './OperationsLayout'

const zero = { gross: '0.00', tax: '0.00', other_deductions: '0.00', net: '0.00' }
const SALARY: MySalary = {
  employee_name: 'Олег Директоров', has_profile: true,
  profile: { salary_type: 'FIXED', salary_type_display: 'Фиксированный оклад', position: 'Операционный директор', rates: [] },
  totals: { accrued: '98000.00', deducted: '9800.00', net: '88200.00', paid: '50000.00', due: '38200.00', pending_approval: '0.00', estimated: '0.00', estimated_deductions: null, estimated_deductions_note: '' },
  deductions: [],
  earnings: {
    as_of: '2026-10-10', schedule: [], not_included: { ...zero, note: '', items: [] }, earned: zero,
    official: { gross: '98000.00', tax: '9800.00', other_deductions: '0.00', net: '88200.00' }, paid: '50000.00',
    company_owes: '38200.00', earned_unpaid: '0.00', next_payment_date: '2026-10-10', difference: '0.00', difference_reasons: [], items: [], deductions: [],
  },
  next_planned_payment_date: '2026-10-10', estimates: [], last_payment: null,
  current_month: { year: 2026, month: 10, label: 'Октябрь 2026', accrued: '0.00', periods: [] },
  history: [{
    payroll_id: 31, year: 2026, month: 9, period_type: 'MONTH', period_label: 'Сентябрь 2026', status: 'PARTIALLY_PAID', status_display: 'Частично выплачено', is_final: true,
    base_amount: '90000.00', bonuses: '10000.00', accrued: '98000.00', paid: '50000.00', due: '38200.00', deducted: '9800.00',
    lines: [{ description: 'Оклад за сентябрь', amount: '90000.00' }],
    adjustments: [{ kind: 'Премия / доплата', reason: 'Премия за KPI', amount: '10000.00' }, { kind: 'Удержание', reason: 'Аванс в счёт', amount: '-2000.00' }],
    deductions: [], planned_payment_date: '2026-10-10',
  }],
  payments: [{ id: 4, payment_date: '2026-09-25', amount: '50000.00', method: 'Банковский перевод', is_advance: false, reference: '', period_label: 'Сентябрь 2026', payroll_id: 31, comment: 'Первая часть, остаток — 10.10' }],
  filters: { year: null, month: null, period_type: null },
}

function render(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/my-salary" element={<MySalaryRedirect />} />
      <Route path="/operations" element={<OperationsLayout />}>
        <Route index element={<p>Dashboard</p>} />
        <Route path="my-salary" element={<MySalaryPage />} />
      </Route>
    </Routes>,
    { route },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(accountingApi.mySalary).mockResolvedValue(SALARY)
})

describe('«Моя зарплата» в кабинете операционного директора', () => {
  it('пункт в нижнем разделе меню рядом с «Моя отметка прихода»', () => {
    render('/operations')
    const nav = screen.getAllByRole('navigation', { name: 'Разделы кабинета операционного директора' })[0]
    const footer = nav.parentElement?.querySelector('.border-t') as HTMLElement
    const links = within(footer).getAllByRole('link').map((a) => a.textContent)
    expect(links).toEqual(['Мои задачи', 'Все сотрудники', 'Моя отметка прихода', 'Моя зарплата'])
    expect(within(footer).getByRole('link', { name: 'Моя зарплата' })).toHaveAttribute('href', '/operations/my-salary')
    expect(within(nav).queryByRole('link', { name: 'Моя зарплата' })).not.toBeInTheDocument()
  })

  it('показывает свои начисления, разбивку, выплаты и комментарий бухгалтера; запрос — без id сотрудника', async () => {
    render('/operations/my-salary')
    expect(await screen.findByRole('heading', { name: 'Моя зарплата' })).toBeInTheDocument()
    expect(accountingApi.mySalary).toHaveBeenCalledWith({})
    for (const label of ['Официально начислено', 'Фактически выплачено', 'Остаток к выплате', 'Ближайшая дата выплаты']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    const table = screen.getAllByRole('table').find((t) => within(t).queryByText('Основная зарплата')) as HTMLElement
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(
      ['Период', 'Основная зарплата', 'Бонусы', 'Удержания', 'Начислено', 'Выплачено', 'Остаток', 'Статус', 'Плановая выплата'])
    const row = within(table).getByText('Сентябрь 2026').closest('tr') as HTMLElement
    expect(row).toHaveTextContent(/90\s000/)
    expect(row).toHaveTextContent(/10\s000/)
    expect(row).toHaveTextContent('Частично выплачено')
    expect(screen.getAllByText('Первая часть, остаток — 10.10').length).toBeGreaterThan(0)
  })

  it('короткий адрес /my-salary ведёт в кабинет операционного директора', async () => {
    render('/my-salary')
    expect(await screen.findByRole('heading', { name: 'Моя зарплата' })).toBeInTheDocument()
  })
})
