import { apiClient } from '@/api/client'
import { newIdempotencyKey } from '@/api/accounting'
import type { Paginated } from '@/types/common'
import type {
  BillingCapabilities,
  BillingDashboard,
  BillingFilters,
  BillingOptions,
  BillingPayment,
  ContactBody,
  ContactRow,
  DebtorRow,
  Invoice,
  PaymentBody,
  TermsChange,
} from '@/types/billing'

const BASE = '/accounting/billing'

type Params = Record<string, string | number | boolean | undefined | null>

const get = <T>(url: string, params?: Params) => apiClient.get<T>(`${BASE}${url}`, { params }).then((r) => r.data)
const post = <T>(url: string, body?: unknown, headers?: Record<string, string>) =>
  apiClient.post<T>(`${BASE}${url}`, body, { headers }).then((r) => r.data)

export const billingApi = {
  me: () => get<BillingCapabilities>('/me/'),
  options: () => get<BillingOptions>('/options/'),
  dashboard: (filters: BillingFilters) => get<BillingDashboard>('/dashboard/', { ...filters }),
  debts: (filters: BillingFilters) => get<{ count: number; results: DebtorRow[] }>('/debts/', { ...filters }),
  invoices: (filters: BillingFilters & { page?: number; unpaid?: boolean }) =>
    get<Paginated<Invoice>>('/invoices/', { ...filters }),
  payments: (filters: BillingFilters & { page?: number }) => get<Paginated<BillingPayment>>('/payments/', { ...filters }),
  contacts: (filters: BillingFilters & { page?: number }) => get<Paginated<ContactRow>>('/contacts/', { ...filters }),
  termsChanges: (status = 'PENDING') => get<Paginated<TermsChange>>('/terms-changes/', { status }),
  /** Повторная отправка формы не создаёт второй платёж: ключ живёт, пока открыта форма. */
  recordPayment: (body: PaymentBody, idempotencyKey: string = newIdempotencyKey()) =>
    post<BillingPayment>('/payments/', body, { 'Idempotency-Key': idempotencyKey }),
  reversePayment: (id: number, reason: string) => post<BillingPayment>(`/payments/${id}/reverse/`, { reason }),
  addContact: (body: ContactBody) => post<ContactRow>('/contacts/', body),
  decideTerms: (id: number, approve: boolean, comment = '') =>
    post<TermsChange>(`/terms-changes/${id}/decide/`, { approve, comment }),
}
