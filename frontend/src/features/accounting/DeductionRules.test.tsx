import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeductionRulesSection } from '@/features/accounting/DeductionRulesSection'
import { renderWithProviders } from '@/test/testUtils'
import type { AccountingOptions, DeductionRule } from '@/types/accounting'

vi.mock('@/api/accounting', () => ({
  accountingApi: {
    deductionRules: vi.fn(),
    createDeductionRule: vi.fn(),
    changeDeductionRule: vi.fn(),
    deductionRuleHistory: vi.fn(),
  },
}))

import { accountingApi } from '@/api/accounting'

const OPTIONS = {
  can_view: true, can_operate: true, can_approve: false,
  employees: [{ id: 9, full_name: 'Айбек Оклад', role: 'assistant' }],
  departments: [{ value: 'IT', label: 'IT' }, { value: 'ASSISTANT', label: 'Ассистенты' }],
} as unknown as AccountingOptions

function rule(patch: Partial<DeductionRule> = {}): DeductionRule {
  return {
    id: 4, series: 's', name: 'Налог', kind: 'TAX', kind_display: 'Налог', calc_type: 'FIXED', calc_type_display: 'Фиксированная сумма',
    amount: '3000.00', frequency: 'MONTHLY', frequency_display: 'Ежемесячно', scope: 'EMPLOYEE', scope_display: 'Сотрудник',
    employee: 9, employee_name: 'Айбек Оклад', department: '', department_display: '', effective_from: '2026-10-01',
    effective_to: null, is_active: true, description: '', previous_version: null, next_version: null,
    usage: { locked_payrolls: 0, draft_payrolls: 0, used_until: null, can_correct: true },
    created_by_name: 'Бухгалтер', created_at: '', updated_at: '', ...patch,
  }
}

const EFFECTS = { payrolls_recalculated: [12], payrolls_failed: [] }

describe('DeductionRulesSection', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists rules with amount, whom and frequency', async () => {
    vi.mocked(accountingApi.deductionRules).mockResolvedValue({ count: 1, next: null, previous: null, results: [rule()] })
    renderWithProviders(<DeductionRulesSection options={OPTIONS} canEdit />)
    const row = (await screen.findByText('Айбек Оклад')).closest('tr')!
    expect(within(row).getByText('3 000 сом')).toBeInTheDocument()
    expect(within(row).getByText('Ежемесячно')).toBeInTheDocument()
    expect(within(row).getByText('Включено')).toBeInTheDocument()
    expect(accountingApi.deductionRules).toHaveBeenCalledWith({ current: true })
  })

  it('creates a fixed monthly deduction for an employee', async () => {
    vi.mocked(accountingApi.deductionRules).mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
    vi.mocked(accountingApi.createDeductionRule).mockResolvedValue({ rule: rule(), effects: EFFECTS })
    const user = userEvent.setup()
    renderWithProviders(<DeductionRulesSection options={OPTIONS} canEdit />)
    await user.click(await screen.findByRole('button', { name: 'Добавить удержание' }))
    await user.type(screen.getByLabelText(/Название/), 'Налог')
    await user.type(screen.getByLabelText(/Сумма, сом/), '3000')
    await user.selectOptions(screen.getByLabelText(/^Сотрудник/), '9')
    await user.click(screen.getByRole('button', { name: 'Добавить' }))
    await waitFor(() => expect(accountingApi.createDeductionRule).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Налог', kind: 'TAX', amount: '3000', frequency: 'MONTHLY', scope: 'EMPLOYEE', employee: 9, department: '',
    })))
  })

  it('changing a rule already in approved payrolls warns and requires a reason; sends only changed fields', async () => {
    const used = rule({ usage: { locked_payrolls: 1, draft_payrolls: 0, used_until: '2026-10-31', can_correct: false } })
    vi.mocked(accountingApi.deductionRules).mockResolvedValue({ count: 1, next: null, previous: null, results: [used] })
    vi.mocked(accountingApi.changeDeductionRule).mockResolvedValue({ rule: used, effects: EFFECTS })
    const user = userEvent.setup()
    renderWithProviders(<DeductionRulesSection options={OPTIONS} canEdit />)
    await user.click(await screen.findByRole('button', { name: 'Изменить' }))
    expect(screen.getByText(/уже вошло в утверждённые расчёты/)).toBeInTheDocument()
    const amount = screen.getByLabelText(/Сумма, сом/)
    await user.clear(amount)
    await user.type(amount, '4000')
    expect(screen.getByLabelText(/Новая версия действует с/)).toBeInTheDocument()
    const from = screen.getByLabelText(/Новая версия действует с/)
    await user.clear(from)
    await user.type(from, '2026-11-01')
    const save = screen.getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled()
    await user.type(screen.getByLabelText(/Причина изменения/), 'рост ставки')
    await user.click(save)
    await waitFor(() => expect(accountingApi.changeDeductionRule).toHaveBeenCalledWith(4, {
      reason: 'рост ставки', amount: '4000', effective_from: '2026-11-01',
    }))
  })

  it('read-only users see no create or change buttons', async () => {
    vi.mocked(accountingApi.deductionRules).mockResolvedValue({ count: 1, next: null, previous: null, results: [rule()] })
    renderWithProviders(<DeductionRulesSection options={OPTIONS} canEdit={false} />)
    await screen.findByText('Айбек Оклад')
    expect(screen.queryByRole('button', { name: 'Добавить удержание' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'История' })).toBeInTheDocument()
  })
})
