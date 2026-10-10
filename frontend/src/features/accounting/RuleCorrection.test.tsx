import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RuleCorrectionModal } from '@/features/accounting/RuleCorrectionModal'
import { SalarySettingsPage } from '@/features/accounting/SalarySettingsPage'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, RuleUsage, SalaryProfile, SalaryRule } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: { correctRule: vi.fn(), replaceRule: vi.fn(), profiles: vi.fn(), options: vi.fn() },
}))

import { accountingApi } from '@/api/accounting'

const OPTIONS = {
  employees: [], courses: [{ id: 1, name: 'Программатика' }], groups: [{ id: 5, name: 'Prog SOFT 1', course: 1, status: 'active' }],
  salary_types: [], departments: [], methods: { FIXED: [], PERCENT: [] }, can_operate: true,
} as unknown as AccountingOptions

const FREE: RuleUsage = { can_correct: true, locked_payrolls: 0, draft_payrolls: 1, locked_accruals: 0, open_accruals: 0, used_until: null }
const USED: RuleUsage = { can_correct: false, locked_payrolls: 1, draft_payrolls: 0, locked_accruals: 0, open_accruals: 0, used_until: '2026-09-30' }

function rule(usage: RuleUsage, id = 7): SalaryRule {
  return {
    id, employee_profile: 3, employee: 9, employee_name: 'Марат Тренеров', rule_type: 'FIXED', rule_type_display: 'Оклад',
    amount: '30000.00', percentage: null, program: null, program_name: null, group: null, group_name: null,
    calculation_method: 'MONTHLY', calculation_method_display: 'Полный месячный оклад', first_half_share: '50.00',
    description: '', effective_from: '2026-01-01', effective_to: null, is_active: true, previous_version: null,
    next_version: null, usage, created_at: '',
  }
}

const EFFECTS = { accruals_updated: 0, accruals_cancelled: 0, payrolls_recalculated: [12], payrolls_voided: [], payrolls_failed: [] }

describe('RuleCorrectionModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('corrects an unused FIXED rule into PERCENT with a required reason', async () => {
    vi.mocked(accountingApi.correctRule).mockResolvedValue({ rule: rule(FREE), effects: EFFECTS })
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<RuleCorrectionModal rule={rule(FREE)} options={OPTIONS} onClose={onClose} />)
    expect(screen.getByText(/можно исправить на месте/)).toBeInTheDocument()
    expect(screen.getByText(/Черновых расчётов с этим правилом: 1/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText(/Тип оплаты/), 'PERCENT')
    expect(screen.getByText(/Тип оплаты сотрудника тоже изменится/)).toBeInTheDocument()
    await user.type(screen.getByLabelText(/Процент тренера/), '10')
    const submit = screen.getByRole('button', { name: 'Исправить правило' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/Что и почему исправляется/), 'Ошибочно выбран оклад')
    await user.click(submit)
    await waitFor(() => expect(accountingApi.correctRule).toHaveBeenCalledWith(7, expect.objectContaining({
      rule_type: 'PERCENT', percentage: '10', amount: null, reason: 'Ошибочно выбран оклад',
    })))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(accountingApi.replaceRule).not.toHaveBeenCalled()
  })

  it('offers replacing a used rule from a date after its approved history', async () => {
    vi.mocked(accountingApi.replaceRule).mockResolvedValue({ rule: rule(FREE, 8), effects: EFFECTS })
    const user = userEvent.setup()
    renderWithProviders(<RuleCorrectionModal rule={rule(USED)} options={OPTIONS} onClose={vi.fn()} />)
    expect(screen.getByText(/история не меняется/)).toBeInTheDocument()
    expect(screen.getByText('Не раньше 01.10.2026')).toBeInTheDocument()
    await user.clear(screen.getByLabelText(/Новое правило действует с/))
    await user.type(screen.getByLabelText(/Новое правило действует с/), '2026-10-10')
    await user.selectOptions(screen.getByLabelText(/Тип оплаты/), 'PERCENT')
    // Смена типа — с 1-го числа: дата сдвигается на начало следующего месяца.
    expect(screen.getByLabelText(/Новое правило действует с/)).toHaveValue('2026-11-01')
    await user.type(screen.getByLabelText(/Процент тренера/), '10')
    await user.type(screen.getByLabelText(/Причина замены/), 'Нужен процент')
    await user.click(screen.getByRole('button', { name: 'Заменить с даты' }))
    await waitFor(() => expect(accountingApi.replaceRule).toHaveBeenCalledWith(7, expect.objectContaining({
      rule_type: 'PERCENT', effective_from: '2026-11-01', reason: 'Нужен процент',
    })))
    expect(accountingApi.correctRule).not.toHaveBeenCalled()
  })

  it('shows the backend validation error and keeps the dialog open', async () => {
    vi.mocked(accountingApi.correctRule).mockRejectedValue({
      isAxiosError: true, response: { status: 400, data: { detail: 'Пересекается с правилом #5' } },
    })
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<RuleCorrectionModal rule={rule(FREE)} options={OPTIONS} onClose={onClose} />)
    await user.type(screen.getByLabelText(/Что и почему исправляется/), 'даты')
    await user.click(screen.getByRole('button', { name: 'Исправить правило' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('SalarySettingsPage rule actions', () => {
  it('shows «Исправить» for unused rules and «Заменить с даты» for used ones', async () => {
    const profile = {
      id: 3, employee: 9, employee_name: 'Марат Тренеров', employee_role: 'teacher', position: '', display_position: 'Тренер',
      salary_type: 'FIXED', salary_type_display: 'Фиксированный оклад', department: '', effective_department: 'OTHER',
      department_display: 'Прочий персонал', currency: 'KGS', is_active: true, effective_from: '2026-01-01', effective_to: null,
      rules: [rule(FREE, 7), { ...rule(USED, 6), effective_to: '2025-12-31' }],
    } as unknown as SalaryProfile
    vi.mocked(accountingApi.profiles).mockResolvedValue({ count: 1, next: null, previous: null, results: [profile] })
    vi.mocked(accountingApi.options).mockResolvedValue(OPTIONS)
    renderWithProviders(<SalarySettingsPage />)
    expect(await screen.findByRole('button', { name: 'Исправить' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Заменить с даты' })).toBeInTheDocument()
    expect(screen.getByText('в утверждённых начислениях до 30.09.2026')).toBeInTheDocument()
  })
})
