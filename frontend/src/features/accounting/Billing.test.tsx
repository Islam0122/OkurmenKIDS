import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BillingPage } from '@/features/accounting/BillingPage'
import { renderWithProviders } from '@/test/testUtils'
import type { BillingCapabilities, BillingDashboard, BillingOptions, InvoiceRow } from '@/types/billing'

vi.mock('@/api/billing', () => ({
  billingApi: {
    me: vi.fn(), options: vi.fn(), dashboard: vi.fn(), debts: vi.fn(), invoices: vi.fn(), payments: vi.fn(),
    contacts: vi.fn(), termsChanges: vi.fn(), recordPayment: vi.fn(), reversePayment: vi.fn(), addContact: vi.fn(),
    decideTerms: vi.fn(),
  },
}))

import { billingApi } from '@/api/billing'

const ROW: InvoiceRow = {
  invoice: 11, number: 'INV-2026-000011', profile: 5, student: 3, student_name: 'Айбек Test', group: 'Group A',
  subject: 'IT', package_number: 2, amount: '4000.00', paid: '2500.00', balance: '1500.00', due_date: '2026-10-23',
  status: 'PARTIALLY_PAID', status_display: 'Частично оплачено', parent_phone: '+996', accountant: 2,
}

const DASHBOARD: BillingDashboard = {
  date: '2026-10-21', date_from: '2026-10-01', date_to: '2026-10-21', active_students: 40, students_awaiting: 7,
  invoices_awaiting: 9, total_debt: '28500.00', overdue_invoices: 3, overdue_students: 2, overdue_amount: '9000.00',
  due_soon_days: 3, due_soon: [ROW], received: { amount: '52000.00', count: 13, refunds: '1000.00', refunds_count: 1, net: '51000.00' },
  credit_total: '3000.00', credit_profiles: 2, partial: [ROW], packages_ending: 4, open_tasks: 9, follow_ups_due: 2, contacts: [],
}

const CAPS: BillingCapabilities = {
  can_view: true, can_view_money: true, is_manager: false, is_accountant: true, is_billing_admin: false,
  can_record_payments: true, can_manage_plans: false, max_manager_discount_percent: '10',
}

describe('BillingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(billingApi.me).mockResolvedValue(CAPS)
    vi.mocked(billingApi.options).mockResolvedValue({
      plans: [], subjects: [{ id: 1, name: 'IT' }], groups: [{ id: 1, name: 'Group A' }], accountants: [],
      invoice_statuses: [{ value: 'OVERDUE', label: 'Просрочено' }], contact_channels: [], contact_results: [],
    } as BillingOptions)
    vi.mocked(billingApi.dashboard).mockResolvedValue(DASHBOARD)
    vi.mocked(billingApi.recordPayment).mockResolvedValue({} as never)
  })

  it('separates students, invoices and debt on the dashboard', async () => {
    renderWithProviders(<BillingPage />)
    expect(await screen.findByText('Студентов ожидают оплаты')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText(/9 начисл\. · активных студентов 40/)).toBeInTheDocument()
    expect(screen.getByText('28 500 сом')).toBeInTheDocument()
    expect(screen.getByText('51 000 сом')).toBeInTheDocument()
    expect(screen.getAllByText('INV-2026-000011')).toHaveLength(2)
  })

  it('records a payment with one idempotency key per open form', async () => {
    const user = userEvent.setup()
    renderWithProviders(<BillingPage />)
    const row = (await screen.findAllByText('INV-2026-000011'))[0].closest('tr')!
    await user.click(row.querySelector('button')!)
    await user.type(screen.getByLabelText(/Сумма, сом/), '1500')
    await user.click(screen.getByRole('button', { name: 'Зарегистрировать' }))
    await waitFor(() => expect(billingApi.recordPayment).toHaveBeenCalledTimes(1))
    const [body, key] = vi.mocked(billingApi.recordPayment).mock.calls[0]
    expect(body).toMatchObject({ profile: 5, amount: '1500', prepay_packages: 0 })
    expect(typeof key).toBe('string')
  })

  it('hides money actions from a manager', async () => {
    vi.mocked(billingApi.me).mockResolvedValue({ ...CAPS, can_record_payments: false, is_accountant: false, is_manager: true })
    renderWithProviders(<BillingPage />)
    const row = (await screen.findAllByText('INV-2026-000011'))[0].closest('tr')!
    expect(row.querySelector('button')).toBeNull()
  })
})
