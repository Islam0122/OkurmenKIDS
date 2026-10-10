import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AnalyticsPage } from '@/features/accounting/AnalyticsPage'
import { BlockReviewSection } from '@/features/accounting/BlockReviewSection'
import { PaymentModal } from '@/features/accounting/PayrollDetailPage'
import { PricingPage } from '@/features/accounting/PricingPage'
import { ReportsPage } from '@/features/accounting/ReportsPage'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, AnalyticsSummary, CycleAccrual, PayrollDetail, TeacherReport } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  newIdempotencyKey: () => 'key-1',
  accountingApi: {
    options: vi.fn(),
    courseSettings: vi.fn(),
    pricing: vi.fn(),
    createPrice: vi.fn(),
    analyticsSummary: vi.fn(),
    teacherReport: vi.fn(),
    downloadTeacherReport: vi.fn(),
    cycleAccruals: vi.fn(),
    reviewCycleAccrual: vi.fn(),
    estimates: vi.fn(),
  },
}))

import { accountingApi } from '@/api/accounting'

const OPTIONS = {
  employees: [], courses: [], groups: [], salary_types: [], rule_types: [], methods: {}, payment_methods: [],
  student_payment_methods: [], adjustment_kinds: [], payroll_statuses: [], student_count_rules: [], subjects: [],
  departments: [{ value: 'IT', label: 'IT' }, { value: 'ENGLISH', label: 'Английский' }],
  can_view: true, can_operate: true, can_approve: false,
} as unknown as AccountingOptions
const DIRECTOR = { ...OPTIONS, can_operate: false, can_approve: true }
const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

const SETTINGS = {
  id: 1, course: 7, course_name: 'Prog SOFT', course_count_lesson: 48, price_per_student: '10000.00', current_price: '10000.00',
  counted_subjects: [], counted_subjects_names: [], required_lessons: 12, count_lessons_from: null,
  student_count_rule: 'ON_COMPLETION', student_count_rule_display: 'на дату завершения', is_active: true, updated_at: '',
}

describe('PricingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountingApi.courseSettings).mockResolvedValue(page([SETTINGS]))
    vi.mocked(accountingApi.pricing).mockResolvedValue(page([{
      id: 3, course: 7, course_name: 'Prog SOFT', price_per_student: '10000.00', currency: 'KGS', effective_from: '2000-01-01',
      effective_to: null, reason: 'Перенесено', previous_version: null, is_migrated: true, is_current: true, created_by: null,
      created_by_name: 'система (перенос данных)', created_at: '2026-10-01T10:00:00Z',
    }]))
  })

  it('saves a new tariff only after explicit confirmation, with a reason', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(accountingApi.createPrice).mockResolvedValue({} as never)
    const user = userEvent.setup()
    renderWithProviders(<PricingPage />)
    expect(await screen.findByText('перенесено — проверьте')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Изменить цену' }))
    const save = screen.getByRole('button', { name: 'Сохранить' })
    await user.type(screen.getByLabelText(/Цена за ученика/), '12000')
    expect(save).toBeDisabled() // без причины нельзя
    await user.type(screen.getByLabelText(/Причина изменения/), 'Новый учебный год')
    await user.click(save)
    expect(accountingApi.createPrice).not.toHaveBeenCalled()
    expect(await screen.findByText('Подтвердите новый тариф')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }))
    await waitFor(() => expect(accountingApi.createPrice).toHaveBeenCalled())
    expect(vi.mocked(accountingApi.createPrice).mock.calls[0][0])
      .toMatchObject({ course: 7, price_per_student: '12000', reason: 'Новый учебный год' })
  })

  it('is read-only for the director', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue(DIRECTOR)
    renderWithProviders(<PricingPage />)
    expect((await screen.findAllByText('Prog SOFT', { selector: 'td' })).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /Новый тариф|Изменить цену/ })).not.toBeInTheDocument()
  })
})

const SUMMARY: AnalyticsSummary = {
  year: 2026, month: 9, accrued: '30000.00', paid: '24000.00', outstanding: '6000.00', awaiting_approval_amount: '0.00',
  employees: 2, cash_paid_in_month: '4000.00',
  previous_month: { year: 2026, month: 8, accrued: '25000.00', paid: '25000.00', outstanding: '0.00', employees: 2 },
  accrued_change: '5000.00', accrued_change_percent: '20.0',
  by_department: [
    { department: 'IT', label: 'IT', accrued: '10000.00', paid: '4000.00', outstanding: '6000.00', employees: 1 },
    { department: 'ENGLISH', label: 'Английский', accrued: '0.00', paid: '0.00', outstanding: '0.00', employees: 0 },
  ],
  pending_approval_count: 1, review_required_count: 2, completed_cycles_without_accrual: 0, open_cycles: 3,
  upcoming_payments: [{ payroll_id: 5, employee: 9, employee_name: 'Trainer Test', period_label: '01.09.2026–15.09.2026',
    planned_payment_date: '2026-09-15', due: '6000.00', status: 'PARTIALLY_PAID', status_display: 'Частично выплачен', is_overdue: true }],
  history: [
    { year: 2026, month: 8, accrued: '25000.00', paid: '25000.00', outstanding: '0.00', cash_paid: '25000.00' },
    { year: 2026, month: 9, accrued: '30000.00', paid: '24000.00', outstanding: '6000.00', cash_paid: '4000.00' },
  ],
}

describe('AnalyticsPage', () => {
  it('shows backend KPIs, departments and overdue payouts without any edit action', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue(DIRECTOR)
    vi.mocked(accountingApi.analyticsSummary).mockResolvedValue(SUMMARY)
    const user = userEvent.setup()
    renderWithProviders(<AnalyticsPage />)
    expect(await screen.findByText('Начислено за месяц')).toBeInTheDocument()
    expect(screen.getAllByText(/30\s000\sсом/).length).toBeGreaterThan(0)
    expect(screen.getByText('переводов в этом месяце: 4 000 сом')).toBeInTheDocument()
    expect(screen.getByText('просрочено')).toBeInTheDocument()
    expect(screen.getByText(/Блоки на проверке: 2/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Зарегистрировать|Утвердить|Изменить/ })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Направление'), 'IT')
    await waitFor(() => expect(accountingApi.analyticsSummary).toHaveBeenLastCalledWith(expect.objectContaining({ department: 'IT' })))
  })
})

const REPORT: TeacherReport = {
  year: 2026, month: 9, range_label: '01.09.2026–30.09.2026', count: 30, next: '?page=2', previous: null,
  results: [{
    payroll_id: 5, employee: 9, employee_name: 'Trainer Test', department: 'IT', department_display: 'IT',
    period_label: '01.09.2026–15.09.2026', period_type: 'FIRST_HALF', salary_type: 'PERCENT', salary_type_display: 'Процент',
    status: 'PARTIALLY_PAID', status_display: 'Частично выплачен', planned_payment_date: '2026-09-15',
    lines: [
      { line_id: 1, line_type: 'PERCENT', line_type_display: '', description: '', group: 1, group_name: 'Python A', course_name: '',
        students: 10, price_per_student: '10000.00', percentage: '10.00', lessons_done: 12, target_lessons: 12, completed_on: null,
        rate: null, accrued: '10000.00' },
      { line_id: 2, line_type: 'PERCENT', line_type_display: '', description: '', group: 2, group_name: 'Python B', course_name: '',
        students: 5, price_per_student: '10000.00', percentage: '10.00', lessons_done: 12, target_lessons: 12, completed_on: null,
        rate: null, accrued: '5000.00' },
    ],
    accrued: '15000.00', adjustments: '0.00', total: '15000.00', paid: '13000.00', due: '2000.00',
  }],
  totals: { accrued: '15000.00', adjustments: '0.00', total: '15000.00', paid: '13000.00', due: '2000.00' },
  by_department: [{ department: 'IT', label: 'IT', accrued: '15000.00', paid: '13000.00', due: '2000.00' }],
  by_group: [{ group_name: 'Python A', accrued: '10000.00' }, { group_name: 'Python B', accrued: '5000.00' }],
  note: 'Выплаты учитываются по расчёту целиком и между группами не делятся.',
}

describe('ReportsPage', () => {
  it('shows payments once per payroll, paginates on the server and exports with filters', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(accountingApi.teacherReport).mockResolvedValue(REPORT)
    const user = userEvent.setup()
    renderWithProviders(<ReportsPage />)
    const total = await screen.findByText('Итого: Trainer Test')
    const totalRow = total.closest('tr')!
    expect(within(totalRow).getByText(/13\s000\sсом/)).toBeInTheDocument()
    expect(within(totalRow).getByText(/2\s000\sсом/)).toBeInTheDocument()
    // «13 000» встречается только в итоге расчёта, итоге месяца и итоге по направлению — не в строках групп.
    expect(screen.getAllByText(/^13\s000\sсом$/)).toHaveLength(3)
    await user.click(screen.getByRole('button', { name: 'Следующая страница' }))
    await waitFor(() => expect(accountingApi.teacherReport).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
    await user.click(screen.getByRole('button', { name: 'XLSX' }))
    expect(accountingApi.downloadTeacherReport).toHaveBeenCalledWith('xlsx', expect.objectContaining({ year: expect.any(Number) }))
  })

  it('shows an empty state for a month without accruals', async () => {
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
    vi.mocked(accountingApi.teacherReport).mockResolvedValue({ ...REPORT, count: 0, results: [] })
    renderWithProviders(<ReportsPage />)
    expect(await screen.findByText('За выбранный месяц начислений нет')).toBeInTheDocument()
  })
})

const REVIEW: CycleAccrual = {
  id: 11, cycle: 4, cycle_number: 2, group: 1, group_name: 'Python A', course_name: 'Prog SOFT', employee: 9,
  employee_name: 'Trainer Test', status: 'REVIEW_REQUIRED', status_display: 'Требует проверки', lessons: 12, lessons_total: 24,
  completed_on: '2026-09-24', student_count: 10, course_price: '10000.00', percentage: '10.00', amount: '10000.00',
  planned_payment_date: '2026-10-01', payroll: null, review_reasons: ['Смена тренера внутри цикла'], note: '',
  reviewed_by_name: '', reviewed_at: null, created_at: '',
}

describe('BlockReviewSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountingApi.cycleAccruals).mockResolvedValue(page([REVIEW]))
  })

  it('lets the accountant confirm a disputed block only with a reason', async () => {
    vi.mocked(accountingApi.reviewCycleAccrual).mockResolvedValue({ ...REVIEW, status: 'ACCRUED' })
    const user = userEvent.setup()
    renderWithProviders(<BlockReviewSection canOperate />)
    expect(await screen.findByText('• Смена тренера внутри цикла')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Подтвердить начисление' }))
    const confirm = screen.getByRole('button', { name: 'Подтвердить' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText(/Причина/), 'Замена согласована')
    await user.click(confirm)
    await waitFor(() => expect(accountingApi.reviewCycleAccrual).toHaveBeenCalledWith(11, true, 'Замена согласована'))
  })

  it('shows no decision buttons to read-only roles', async () => {
    renderWithProviders(<BlockReviewSection canOperate={false} />)
    expect(await screen.findByText('• Смена тренера внутри цикла')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /начисление/ })).not.toBeInTheDocument()
  })
})

describe('PaymentModal', () => {
  it('rejects amounts above the remaining balance and zero', async () => {
    const onSubmit = vi.fn().mockResolvedValue(true)
    const user = userEvent.setup()
    renderWithProviders(
      <PaymentModal payroll={{ id: 1, amount_due: '2000.00' } as PayrollDetail} isOpen onClose={vi.fn()} onSubmit={onSubmit}
        methods={[{ value: 'bank', label: 'Банк' }]} />,
    )
    const submit = screen.getByRole('button', { name: 'Зарегистрировать' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/Сумма/), '2000.01')
    expect(screen.getByText('Больше остатка')).toBeInTheDocument()
    expect(submit).toBeDisabled()
    await user.clear(screen.getByLabelText(/Сумма/))
    await user.type(screen.getByLabelText(/Сумма/), '2000')
    await user.click(submit)
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ amount: '2000' }), 'key-1')
  })
})
