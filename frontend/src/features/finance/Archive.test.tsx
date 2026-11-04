import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { buildUser } from '@/test/fixtures'
import { renderWithProviders } from '@/test/testUtils'
import type { ArchiveDetail, ArchivePage as ArchivePageData, FinanceMe, FinanceOptions, RestoreCheck } from '@/types/finance'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: buildUser({ role: 'accountant' }), status: 'authenticated', login: vi.fn(), logout: vi.fn() }),
}))
vi.mock('@/api/finance', () => ({
  financeApi: {
    me: vi.fn(), options: vi.fn(), archive: vi.fn(), archiveStudent: vi.fn(), restoreCheck: vi.fn(), restoreStudent: vi.fn(),
  },
}))

import { financeApi } from '@/api/finance'
import { ArchivePage } from '@/features/finance/ArchivePage'
import { ArchiveStudentPage } from '@/features/finance/ArchiveStudentPage'

const ME: FinanceMe = {
  role: 'accountant', read_only: false, can_view: true, can_view_money: true, is_manager: false, is_accountant: true,
  is_director: false, can_record_payments: true, can_register: true, can_manage_plans: true, can_manage_settings: true,
  can_view_audit: true, max_manager_discount_percent: '10',
}
const OPTIONS = {
  plans: [], programs: [], subjects: [{ id: 1, name: 'IT' }], groups: [{ id: 4, name: 'PRO-01' }], accountants: [],
  invoice_statuses: [], payment_methods: [], payment_modes: [], reservation_modes: [], contract_statuses: [],
  contact_channels: [], contact_results: [],
  deactivation_reasons: [{ value: 'financial_issues', label: 'Финансовые трудности' }, { value: 'relocation', label: 'Переезд' }],
} as FinanceOptions

const FINANCE = {
  contract_price: '30000.00', invoiced: '30000.00', paid: '20000.00', discount: '0.00', adjusted: '0.00',
  debt: '10000.00', due_now: '10000.00', overpayment: '0.00', contracts_count: 1, has_debt: true,
}

const PAGE: ArchivePageData = {
  count: 1, page: 1, page_size: 25,
  statistics: { total: 1, debt_total: '10000.00', with_debt: 1, without_debt: 0, paid_total: '20000.00', overpayment_total: '0.00' },
  results: [{
    id: 12, name: 'Асанов Айбек', group: { id: 4, name: 'PRO-01' }, subjects: ['IT'],
    contracts: [{ id: 31, number: 31, status: 'INACTIVE', status_display: 'Начисления остановлены', subject: 'IT', plan: 'IT курс' }],
    finance: FINANCE, deactivated_on: '2026-11-01', reason: 'financial_issues', reason_display: 'Финансовые трудности',
    status: 'withdrawn', status_display: 'Неактивен',
  }],
}

const EVENT = {
  id: 5, type: 'deactivated', type_display: 'Деактивация', date: '2026-11-01', reason: 'financial_issues',
  reason_display: 'Финансовые трудности', comment: 'Нет денег', group: { id: 4, name: 'PRO-01' }, from_group: null,
  performed_by: { id: 2, name: 'Асель Ассистент' }, created_at: '2026-11-01T10:00:00Z', last_activity_date: null, study_days: 60,
}

function detail(overrides: Partial<ArchiveDetail> = {}): ArchiveDetail {
  return {
    student: { id: 12, name: 'Асанов Айбек', first_name: 'Айбек', last_name: 'Асанов', phone: '', parent_phone: '+996555000111',
      parent_name: 'Асанова А.', last_group: { id: 4, name: 'PRO-01' }, subjects: ['IT'], enrollment_date: '2026-09-01',
      status: 'withdrawn', status_display: 'Деактивирован', is_archived: true },
    deactivation: EVENT,
    finance: FINANCE,
    contracts: [{
      id: 31, number: 31, status: 'INACTIVE', status_display: 'Начисления остановлены', subject: 'IT', plan: 'IT курс',
      payment_mode_display: 'Помесячная оплата', start_date: '2026-09-01', stopped_on: '2026-11-01', stop_reason: 'Деактивация',
      stop_source_display: 'Статус студента в LMS', standard_course_price: '30000.00', final_course_price: '30000.00',
      discount_amount: '0.00', discount_reason: '', parent_name: '', parent_phone: '', responsible_accountant: null,
      totals: { contract_price: '30000.00', invoiced: '30000.00', paid: '20000.00', discount: '0.00', adjusted: '0.00',
        debt: '10000.00', due_now: '10000.00', overpayment: '0.00' },
      terms_history: [], adjustments: [], documents: [],
    }],
    payments: [{ id: 77, date: '2026-10-01', amount: '20000.00', kind: 'payment', kind_display: 'Оплата', method: 'cash',
      method_display: 'Наличные', status: 'confirmed', status_display: 'Подтверждён', accepted_by: { id: 3, name: 'Бухгалтер' },
      comment: 'Октябрь', reference: '', transaction: '№77', receipt: null, contract: 31, created_at: '2026-10-01T10:00:00Z' }],
    invoices: [],
    status_history: [EVENT],
    study: { groups: [{ id: 4, name: 'PRO-01', since: '2026-09-01' }], transfers: [], attended_lessons: 18, last_attendance: '2026-10-30' },
    can_restore: false,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(financeApi.me).mockResolvedValue(ME)
  vi.mocked(financeApi.options).mockResolvedValue(OPTIONS)
})

describe('Архив студентов', () => {
  it('shows KPIs and the archived student with debt from the backend', async () => {
    vi.mocked(financeApi.archive).mockResolvedValue(PAGE)
    renderWithProviders(<ArchivePage />, { route: '/finance/archive' })
    expect(await screen.findByText('Асанов Айбек')).toBeInTheDocument()
    expect(screen.getByText('Долг архива')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Финансовые трудности')).toBeInTheDocument()
    expect(within(table).getByText('Неактивен')).toBeInTheDocument()
    expect(within(table).getByText('№31')).toBeInTheDocument()
  })

  it('sends filters to the backend (debt, reason)', async () => {
    vi.mocked(financeApi.archive).mockResolvedValue(PAGE)
    const user = userEvent.setup()
    renderWithProviders(<ArchivePage />, { route: '/finance/archive' })
    await screen.findByText('Асанов Айбек')
    await user.selectOptions(screen.getByLabelText('Задолженность'), 'yes')
    await waitFor(() => expect(financeApi.archive).toHaveBeenLastCalledWith(expect.objectContaining({ debt: 'yes', page: 1 })))
    await user.selectOptions(screen.getByLabelText('Причина деактивации'), 'relocation')
    await waitFor(() => expect(financeApi.archive).toHaveBeenLastCalledWith(
      expect.objectContaining({ debt: 'yes', reason: 'relocation' })))
  })

  it('empty archive explains where students come from', async () => {
    vi.mocked(financeApi.archive).mockResolvedValue({ ...PAGE, count: 0, results: [] })
    renderWithProviders(<ArchivePage />, { route: '/finance/archive' })
    expect(await screen.findByText('Архив пуст')).toBeInTheDocument()
  })

  it('card: who deactivated, finance, payment history; accountant can take payment but not restore', async () => {
    vi.mocked(financeApi.archiveStudent).mockResolvedValue(detail())
    renderWithProviders(
      <Routes><Route path="/finance/archive/:studentId" element={<ArchiveStudentPage />} /></Routes>,
      { route: '/finance/archive/12' },
    )
    expect(await screen.findByRole('heading', { name: 'Асанов Айбек' })).toBeInTheDocument()
    expect(screen.getByText(/Асель Ассистент/)).toBeInTheDocument()
    expect(screen.getByText(/Финансовые трудности — Нет денег/)).toBeInTheDocument()
    expect(screen.getByText('Остаток задолженности')).toBeInTheDocument()
    expect(screen.getByText('Октябрь')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Принять оплату/ })).toHaveAttribute('href', '/finance/payments/new?profile=31')
    expect(screen.queryByRole('button', { name: /Восстановить/ })).not.toBeInTheDocument()
  })

  it('restore: shows checks, requires a group, then calls the backend', async () => {
    vi.mocked(financeApi.archiveStudent).mockResolvedValue(detail({ can_restore: true }))
    const check: RestoreCheck = {
      can_restore: true, groups: [{ id: 4, name: 'PRO-01', course: 'Python', status: 'active', students_count: 10, max_students: 12 }],
      resumable_contracts: [{ id: 31, subject: 'IT', plan: 'IT курс', status_display: 'Начисления остановлены' }],
      closed_contracts: [], needs_new_contract: false, warnings: [], finance: FINANCE,
    }
    vi.mocked(financeApi.restoreCheck).mockResolvedValue(check)
    vi.mocked(financeApi.restoreStudent).mockResolvedValue(detail())
    const user = userEvent.setup()
    renderWithProviders(
      <Routes><Route path="/finance/archive/:studentId" element={<ArchiveStudentPage />} /></Routes>,
      { route: '/finance/archive/12' },
    )
    await user.click(await screen.findByRole('button', { name: /Восстановить/ }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText(/Возобновятся договоры: №31/)).toBeInTheDocument()
    const confirm = within(dialog).getByRole('button', { name: 'Подтвердить восстановление' })
    expect(confirm).toBeDisabled()
    await user.selectOptions(within(dialog).getByLabelText(/Группа/), '4')
    await user.click(confirm)
    await waitFor(() => expect(financeApi.restoreStudent).toHaveBeenCalledWith(12, expect.objectContaining({ group: 4 })))
  })
})
