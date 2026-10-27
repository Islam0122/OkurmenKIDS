import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { MySalary } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: { mySalary: vi.fn(), downloadMySalaryPdf: vi.fn(), myPayoutPlan: vi.fn().mockResolvedValue({ results: [] }) },
}))
vi.mock('./Reminders', () => ({ RemindersBell: () => null }))
const auth = vi.hoisted(() => ({ role: 'hr_manager' }))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: auth.role, first_name: 'Айгуль', last_name: 'HR' }, status: 'authenticated', logout: vi.fn() }),
}))

import { accountingApi } from '@/api/accounting'
import { MySalaryPage } from '@/features/accounting/MySalaryPage'
import { MySalaryRedirect } from '@/app/router/MySalaryRedirect'

import { HrLayout } from './HrLayout'

const zero = { gross: '0.00', tax: '0.00', other_deductions: '0.00', net: '0.00' }
const EMPTY: MySalary = {
  employee_name: 'Айгуль HR', has_profile: false, profile: null,
  totals: { accrued: '0.00', deducted: '0.00', net: '0.00', paid: '0.00', due: '0.00', pending_approval: '0.00', estimated: '0.00', estimated_deductions: null, estimated_deductions_note: '' },
  deductions: [],
  earnings: {
    as_of: '2026-10-10', schedule: [], not_included: { ...zero, note: '', items: [] }, earned: zero, official: zero, paid: '0.00',
    company_owes: '0.00', earned_unpaid: '0.00', next_payment_date: null, difference: '0.00', difference_reasons: [], items: [], deductions: [],
  },
  next_planned_payment_date: null, estimates: [], last_payment: null,
  current_month: { year: 2026, month: 10, label: 'Октябрь 2026', accrued: '0.00', periods: [] },
  history: [], payments: [], filters: { year: null, month: null, period_type: null },
}

function renderHr(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/my-salary" element={<MySalaryRedirect />} />
      <Route path="/hr" element={<HrLayout />}>
        <Route index element={<p>Главная HR</p>} />
        <Route path="my-salary" element={<MySalaryPage />} />
      </Route>
    </Routes>,
    { route },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  auth.role = 'hr_manager'
  vi.mocked(accountingApi.mySalary).mockResolvedValue(EMPTY)
})

describe('«Моя зарплата» в HR-кабинете', () => {
  it('пункт меню ведёт на свою зарплату', async () => {
    renderHr('/hr')
    const nav = screen.getAllByRole('navigation', { name: 'Навигация HR-кабинета' })[0]
    expect(within(nav).getByRole('link', { name: 'Моя зарплата' })).toHaveAttribute('href', '/hr/my-salary')
  })

  it('без начислений — понятное пустое состояние, без придуманных сумм', async () => {
    renderHr('/hr/my-salary')
    expect(await screen.findByRole('heading', { name: 'Моя зарплата' })).toBeInTheDocument()
    expect(screen.getByText('Начислений пока нет')).toBeInTheDocument()
    expect(screen.getByText('Зарплатный профиль ещё не настроен бухгалтерией.')).toBeInTheDocument()
    // Запрос — без id сотрудника: сервер берёт его из сессии.
    expect(accountingApi.mySalary).toHaveBeenCalledWith({})
  })

  it('короткий адрес /my-salary ведёт HR в его кабинет', async () => {
    renderHr('/my-salary')
    expect(await screen.findByRole('heading', { name: 'Моя зарплата' })).toBeInTheDocument()
    expect(screen.getAllByRole('navigation', { name: 'Навигация HR-кабинета' }).length).toBeGreaterThan(0)
  })
})
