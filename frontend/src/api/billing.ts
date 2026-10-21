import { apiClient } from '@/api/client'
import { newIdempotencyKey } from '@/api/accounting'
import type { Paginated } from '@/types/common'
import type {
  BillingCapabilities,
  BillingDashboard,
  BillingFilters,
  BillingOptions,
  BillingPayment,
  BillingStudent,
  BulkRegisterBody,
  ContactBody,
  ContactRow,
  DebtorRow,
  Invoice,
  PaymentBody,
  PlanCreateBody,
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
  students: (params: { group?: number; search?: string; registered?: string; state?: string; page?: number }) =>
    get<Paginated<BillingStudent>>('/students/', params),
  bulkRegister: (body: BulkRegisterBody) =>
    post<{ created: number; skipped: { student: number; student_name: string; reason: string }[] }>('/profiles/bulk/', body),
  createPlan: (body: PlanCreateBody) => post<{ id: number; name: string }>('/plans/', body),
  decideTerms: (id: number, approve: boolean, comment = '') =>
    post<TermsChange>(`/terms-changes/${id}/decide/`, { approve, comment }),
}
