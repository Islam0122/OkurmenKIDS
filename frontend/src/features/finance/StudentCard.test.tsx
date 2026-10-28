import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { ContractCard, FinanceMe, MonthEditResult, ScheduleMonth } from '@/types/finance'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: 'accountant' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/accounting', () => ({ newIdempotencyKey: () => 'form-key' }))
vi.mock('@/api/finance', () => ({
  financeApi: {
    me: vi.fn(), options: vi.fn(), card: vi.fn(), lessonBreakdown: vi.fn(), editMonth: vi.fn(), monthHistory: vi.fn(),
    credit: vi.fn(), invoice: vi.fn(), applyCredit: vi.fn(),
  },
}))

import { financeApi } from '@/api/finance'
import { StudentCardPage } from '@/features/finance/StudentCardPage'

const ACCOUNTANT: FinanceMe = {
  role: 'accountant', read_only: false, can_view: true, can_view_money: true, is_manager: false, is_accountant: true,
  is_director: false, can_record_payments: true, can_register: true, can_manage_plans: true, can_manage_settings: true,
  can_view_audit: true, max_manager_discount_percent: '10',
}
const DIRECTOR: FinanceMe = { ...ACCOUNTANT, role: 'director', read_only: true, is_accountant: false, is_director: true,
  can_record_payments: false, can_register: false, can_manage_plans: false, can_manage_settings: false }

const editable = (state: 'invoiced' | 'future') => ({ standard: true, plan: state === 'future', charge: state === 'invoiced', blocked: null })

function month(n: number, over: Partial<ScheduleMonth>): ScheduleMonth {
  return { month_number: n, state: 'future', amount: '15000.00', paid: '0.00', balance: '0.00', covered_by_credit: '0.00',
    to_pay: '15000.00', standard_price: n === 1 ? '13000.00' : '15000.00', plan_amount: n === 1 ? '13000.00' : '15000.00',
    standard: n === 1 ? '13000.00' : '15000.00', plan: n === 1 ? '13000.00' : '15000.00', charge: null, adjusted: '0.00',
    allocated: '0.00', ui_status: 'future', manual: false, plan_mismatch: false, editable: editable('future'), ...over }
}

/** Эталон задачи: 58 000 = 13 000 + 15 000 + 15 000 + 15 000; получено 11 000 (в т.ч. бронь 1 000). */
const CARD = {
  contract: { id: 7, student_name: 'Асанов Айбек', parent_name: 'Асанова А.', parent_phone: '+996 555 000 111',
    group_name: 'KC-1', program_name: "Kid's Club", plan_name: "Kid's Club Standard", subject_name: 'IT', status: 'ACTIVE',
    status_display: 'Обучается', is_course: true, payment_mode_display: 'Помесячная оплата',
    reservation_allocation_display: 'Бронь засчитывается в первый месяц', standard_course_price: '58000.00',
    final_course_price: '58000.00', discount_enabled: false, discount_amount: '0.00', discount_reason: '', month_price: '15000.00',
    lessons_per_month: 12, deadline_lessons: 3, start_date: '2026-09-01', duration_months: 4, special_terms: '', pending_terms: null },
  row: { stage: 'overdue' },
  summary: { received: '11000.00', refunded: '0.00', net_received: '11000.00', reservation_received: '1000.00',
    reservation_unused: '0.00', allocated: '11000.00', adjusted: '0.00', credit: '0.00', invoiced: '28000.00',
    invoices_balance: '17000.00', credit_applicable: '0.00', credit_unapplied: '0.00', due_now: '17000.00', overdue: '2000.00',
    paid_total: '11000.00', voided: '0.00', voided_count: 0, credit_reserved_future: '0.00', credit_unreserved: '0.00',
    net_to_pay: '47000.00', standard_course_price: '58000.00', final_course_price: '58000.00', discount_amount: '0.00',
    outstanding: '47000.00', future: '30000.00', course_paid_in_full: false },
  debt: { unpaid_count: 2, overdue_count: 1, next_due: { invoice: 2, number: 'INV-2026-000002', month_number: 2,
    balance: '15000.00', due_lesson: 3, lessons_used: 1, due_date: null } },
  schedule: { month_plan_mode: 'PROPORTIONAL', standard_course_price: '58000.00', discount_amount: '0.00',
    final_course_price: '58000.00', invoiced: '28000.00', projected: '30000.00', total: '58000.00', consistent: true,
    issues: [], price_changes: [], plan_total: '58000.00', plan_difference: '0.00', standard_total: '58000.00',
    edit_blocked: null, version: 'v1',
    months: [
      month(1, { state: 'invoiced', invoice: 1, number: 'INV-2026-000001', amount: '13000.00', charge: '13000.00',
        allocated: '11000.00', paid: '11000.00', balance: '2000.00', ui_status: 'overdue', due_lesson: 3, lessons_used: 12,
        status: 'OVERDUE', editable: editable('invoiced') }),
      month(2, { state: 'invoiced', invoice: 2, number: 'INV-2026-000002', charge: '15000.00', balance: '15000.00',
        ui_status: 'awaiting', due_lesson: 3, lessons_used: 1, status: 'OPEN', editable: editable('invoiced') }),
      month(3, {}), month(4, {}),
    ] },
  progress: null, months: [], reservations: [], payments: [], contacts: [],
  invoices: [
    { id: 1, number: 'INV-2026-000001', kind: 'MONTH', month_number: 1, package_number: 1, amount: '13000.00',
      amount_paid: '11000.00', amount_adjusted: '0.00', balance: '2000.00', status: 'OVERDUE', status_display: 'Просрочено',
      stage: 'overdue', due_lesson: 3, lessons_used: 12, lessons_total: 12, due_date: '2026-09-01' },
    { id: 2, number: 'INV-2026-000002', kind: 'MONTH', month_number: 2, package_number: 2, amount: '15000.00',
      amount_paid: '0.00', amount_adjusted: '0.00', balance: '15000.00', status: 'OPEN', status_display: 'Ожидает оплаты',
      stage: 'awaiting', due_lesson: 3, lessons_used: 1, lessons_total: 12, due_date: '2026-09-20' },
  ],
} as unknown as ContractCard

const state = (plan: string) => ({ standard: '15000.00', plan, charge: null, paid: '0.00', balance: '0.00', invoice: null,
  status: 'future' as const, state: 'future' })
const course = (final: string, future: string, toPay: string) => ({ final_course_price: final, standard_course_price: '58000.00',
  discount_amount: (58000 - Number(final)).toFixed(2), plan_total: final, invoiced: '28000.00', future, due_now: '17000.00',
  overdue: '2000.00', net_to_pay: toPay, credit: '0.00', allocated: '11000.00', received: '11000.00' })
const PREVIEW: MonthEditResult = {
  changed: true, dry_run: true, month_number: 4, warnings: [], version: 'v1', fields: ['plan'],
  month: { before: state('15000.00'), after: state('14000.00') },
  course: { before: course('58000.00', '30000.00', '47000.00'), after: course('57000.00', '29000.00', '46000.00') },
  other_months: [],
}

function openCard() {
  return renderWithProviders(<Routes><Route path="/finance/students/:profileId" element={<StudentCardPage />} /></Routes>,
    { route: '/finance/students/7' })
}

async function openEdit(user: ReturnType<typeof userEvent.setup>, n: number) {
  const table = await screen.findByRole('table', { name: 'График оплаты' })
  await user.click(within(table).getByRole('button', { name: `Действия: месяц №${n}` }))
  await user.click(screen.getByRole('menuitem', { name: 'Изменить' }))
  return screen.getByRole('dialog')
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(financeApi.me).mockResolvedValue(ACCOUNTANT)
  vi.mocked(financeApi.card).mockResolvedValue(CARD)
  vi.mocked(financeApi.lessonBreakdown).mockResolvedValue({ attended: 13, marked: 13, counted: 13, priority_subject: 'IT',
    contract_start: '2026-09-01', totals: { counted: 13 }, priority_before_contract: { count: 0, first_date: null }, lessons: [] })
})

describe('Финансовый профиль ученика — эталонный пример 58 000', () => {
  it('cards: debt 17 000 (2 000 overdue), received 11 000, credit 0, left 47 000 = 17 000 + 30 000', async () => {
    openCard()
    expect(await screen.findByRole('heading', { name: 'Асанов Айбек' })).toBeInTheDocument()
    const breakdown = screen.getByTestId('money-breakdown')
    expect(breakdown).toHaveTextContent(/Получено 11\s000 сом = оплачено по начислениям 11\s000 сом \+ свободный аванс 0/)
    expect(breakdown).toHaveTextContent(/Текущий долг 17\s000 сом \+ будущие начисления 30\s000 сом = осталось оплатить 47\s000/)
    expect(screen.getByTestId('finance-status')).toHaveTextContent(/Долг 17\s000 сом, из них просрочено 2\s000/)
    expect(screen.getByText('Неоплаченных начислений')).toBeInTheDocument()
    expect(screen.getByText(/Ближайший срок: 3-й урок месяца №2 \(сейчас 1\)/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()  // суммы сходятся — без предупреждений
    expect(screen.getByRole('link', { name: '+996 555 000 111' })).toHaveAttribute('href', 'tel:+996555000111')
  })

  it('schedule shows standard, plan and charge separately; future months have no invoice', async () => {
    openCard()
    const table = await screen.findByRole('table', { name: 'График оплаты' })
    const [head, m1, , m3] = within(table).getAllByRole('row')
    expect(head).toHaveTextContent('МесяцСтандартПо плануНачислениеОплаченоОстатокСрокСтатус')
    expect(m1).toHaveTextContent(/№1INV-2026-00000113\s000 сом13\s000 сом13\s000 сом11\s000 сом2\s000 сом3-й урок \(сейчас 12\)Просрочен/)
    expect(m3).toHaveTextContent('Будет выставлен')
    expect(m3).not.toHaveTextContent('INV-')
    expect(screen.getByRole('list', { name: 'Месяцы графика оплаты' })).toBeInTheDocument()  // карточки на телефоне
    expect(screen.getByText('Стоимость по договору')).toBeInTheDocument()
  })

  it('invoice filter shows only overdue invoices', async () => {
    const user = userEvent.setup()
    openCard()
    await screen.findByText('Начисления')
    await user.click(screen.getByRole('radio', { name: 'Просроченные' }))
    const section = screen.getByRole('button', { name: 'Начисления' }).closest('section')!
    expect(section).toHaveTextContent('INV-2026-000001')
    expect(section).not.toHaveTextContent('INV-2026-000002')
  })
})

describe('Изменение сумм месяца', () => {
  it('previews consequences on the server, requires a reason and saves with the schedule version', async () => {
    vi.mocked(financeApi.editMonth).mockResolvedValue(PREVIEW)
    const user = userEvent.setup()
    openCard()
    const dialog = await openEdit(user, 4)
    expect(within(dialog).getByLabelText('Начисление')).toBeDisabled()  // месяц не выставлен
    const plan = within(dialog).getByLabelText('По плану')
    await user.clear(plan)
    await user.type(plan, '14000')
    const preview = await within(dialog).findByTestId('month-edit-preview')
    expect(financeApi.editMonth).toHaveBeenLastCalledWith(7, expect.objectContaining({ month_number: 4, plan_amount: '14000',
      standard_price: null, charge: null, difference: 'course', dry_run: true, version: 'v1' }))
    expect(preview).toHaveTextContent(/Итоговая стоимость курса58\s000 сом57\s000 сом−1\s000 сом/)
    expect(preview).toHaveTextContent(/Осталось оплатить47\s000 сом46\s000 сом/)
    expect(preview).not.toHaveTextContent('Текущий долг')  // долг не меняется — строки нет
    const save = within(dialog).getByRole('button', { name: 'Сохранить изменения' })
    expect(save).toBeDisabled()
    await user.type(within(dialog).getByLabelText(/Причина корректировки/), 'Ошибка в плане')
    await user.click(save)
    await waitFor(() => expect(financeApi.editMonth).toHaveBeenLastCalledWith(7, expect.objectContaining({
      plan_amount: '14000', dry_run: false, reason: 'Ошибка в плане', version: 'v1' })))
  })

  it('a stale version keeps the form open with a clear message and nothing shown as saved', async () => {
    vi.mocked(financeApi.editMonth).mockImplementation(async (_p, body) => {
      if (body.dry_run) return { ...PREVIEW, month_number: 1 }
      throw new AxiosError('conflict', 'ERR', undefined, undefined, { status: 409,
        data: { detail: 'Данные договора изменились, пока форма была открыта.', code: 'stale' } } as AxiosResponse)
    })
    const user = userEvent.setup()
    openCard()
    const dialog = await openEdit(user, 1)
    expect(within(dialog).getByLabelText('По плану')).toBeDisabled()  // выставленный месяц: план = начисление
    const charge = within(dialog).getByLabelText('Начисление')
    await user.clear(charge)
    await user.type(charge, '12000')
    await within(dialog).findByTestId('month-edit-preview')
    await user.type(within(dialog).getByLabelText(/Причина корректировки/), 'ошибка')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить изменения' }))
    expect(await within(dialog).findByText(/Изменения не сохранены: Данные договора изменились/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Обновить данные' })).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Начисление')).toHaveValue('12000')
  })

  it('cancel closes without saving; backend rejection is shown in the preview', async () => {
    vi.mocked(financeApi.editMonth).mockRejectedValue(new AxiosError('bad', 'ERR', undefined, undefined, { status: 400,
      data: { detail: 'Нельзя уменьшить начисление ниже уже оплаченной суммы (11000.00 сом).', code: 'below_paid' } } as AxiosResponse))
    const user = userEvent.setup()
    openCard()
    const dialog = await openEdit(user, 1)
    const charge = within(dialog).getByLabelText('Начисление')
    await user.clear(charge)
    await user.type(charge, '10000')
    expect(await within(dialog).findByText(/ниже уже оплаченной суммы/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Сохранить изменения' })).toBeDisabled()
    await user.click(within(dialog).getByRole('button', { name: 'Отмена' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(vi.mocked(financeApi.editMonth).mock.calls.every(([, body]) => body.dry_run)).toBe(true)
  })

  it('director sees history but cannot edit', async () => {
    vi.mocked(financeApi.me).mockResolvedValue(DIRECTOR)
    vi.mocked(financeApi.monthHistory).mockResolvedValue([{ id: 1, created_at: '2026-10-24T08:00:00Z', actor: 'buh',
      action: 'billing_month_edit', entity_type: 'studentbillingprofile', entity_id: 7, invoice_number: null,
      old_values: { charge: '13000.00', final_course_price: '58000.00' },
      new_values: { fields: ['charge'], charge: '12000', final_course_price: '57000.00', difference: 'course',
        reissued: { from: 'INV-1', to: 'INV-5' } }, reason: 'ошибка' }])
    const user = userEvent.setup()
    openCard()
    const table = await screen.findByRole('table', { name: 'График оплаты' })
    await waitFor(() => expect(financeApi.me).toHaveBeenCalled())
    await user.click(within(table).getByRole('button', { name: 'Действия: месяц №1' }))
    expect(screen.queryByRole('menuitem', { name: 'Изменить' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: 'История изменений' }))
    const dialog = screen.getByRole('dialog')
    expect(await within(dialog).findByText(/Начисление: 13\s000 сом → 12\s000 сом/)).toBeInTheDocument()
    expect(within(dialog).getByText('Начисление INV-1 заменено на INV-5')).toBeInTheDocument()
    expect(within(dialog).getByText('Причина: ошибка')).toBeInTheDocument()
    expect(financeApi.monthHistory).toHaveBeenCalledWith(7, 1)
  })
})
