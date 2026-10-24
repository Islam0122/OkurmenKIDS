import { apiClient } from '@/api/client'
import { newIdempotencyKey } from '@/api/accounting'
import type { Paginated } from '@/types/common'
import type {
  Analytics,
  AuditEntry,
  AuditRow,
  Contract,
  ContractBody,
  ContractCard,
  LessonBreakdown,
  FinanceDashboard,
  FinanceMe,
  FinanceOptions,
  FinanceSettings,
  LmsStudent,
  Payment,
  PaymentBody,
  PaymentCorrection,
  PaymentCorrectionResult,
  PaymentPreview,
  PaymentTarget,
  PeriodReport,
  PeriodsResponse,
  Plan,
  PlanBody,
  QueueCounts,
  QueueFilters,
  QueueKind,
  QueuePage,
  Receipt,
} from '@/types/finance'

const BASE = '/accounting/billing'

type Params = Record<string, string | number | boolean | undefined | null>

const get = <T>(url: string, params?: Params) => apiClient.get<T>(`${BASE}${url}`, { params }).then((r) => r.data)
const post = <T>(url: string, body?: unknown, headers?: Record<string, string>) =>
  apiClient.post<T>(`${BASE}${url}`, body, { headers }).then((r) => r.data)
const patch = <T>(url: string, body?: unknown) => apiClient.patch<T>(`${BASE}${url}`, body).then((r) => r.data)

/** PDF чека — за JWT, поэтому blob; повторная печать ничего не создаёт на сервере. */
async function receiptPdf(id: number, size: 'a4' | 'compact', mode: 'open' | 'download'): Promise<void> {
  const response = await apiClient.get<Blob>(`${BASE}/receipts/${id}/pdf/`, { params: { size }, responseType: 'blob' })
  const href = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
  if (mode === 'open') {
    window.open(href, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(href), 60_000)
    return
  }
  const link = document.createElement('a')
  link.href = href
  link.download = `receipt-${id}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

export const financeApi = {
  me: () => get<FinanceMe>('/me/'),
  options: () => get<FinanceOptions>('/options/'),
  dashboard: () => get<FinanceDashboard>('/dashboard/'),
  periods: () => get<PeriodsResponse>('/periods/'),
  /** `month=ГГГГ-ММ` или `date_from` + `date_to`. */
  periodReport: (params: Params) => get<PeriodReport>('/reports/period/', params),
  counts: () => get<QueueCounts>('/queues/counts/'),
  queue: (queue: QueueKind, filters: QueueFilters) => get<QueuePage>(`/queues/${queue}/`, { ...filters }),
  lmsStudents: (params: { search?: string; group?: number; registered?: string; page?: number }) =>
    get<Paginated<LmsStudent>>('/students/', params),
  card: (profile: number) => get<ContractCard>(`/profiles/${profile}/card/`),
  lessonBreakdown: (profile: number) => get<LessonBreakdown>(`/profiles/${profile}/lessons/`),
  /** Исправить ошибочную дату начала договора (администратор оплаты, с основанием). */
  changeStartDate: (profile: number, body: { start_date: string; reason: string }) =>
    post<{ consumed: number; lessons: LessonBreakdown }>(`/profiles/${profile}/start-date/`, body),
  /** Распределить свободный аванс на неоплаченные начисления договора. */
  applyCredit: (profile: number) => post(`/profiles/${profile}/apply-credit/`),
  /** Двойной клик / повтор формы не создаёт второй договор и не проводит деньги дважды. */
  createContract: (body: ContractBody, idempotencyKey: string = newIdempotencyKey()) =>
    post<Contract>('/profiles/', { ...body, idempotency_key: idempotencyKey }),
  courseTerms: (profile: number, body: { discount_enabled: boolean; final_course_price: string | null; reason: string }) =>
    post(`/profiles/${profile}/course-terms/`, body),
  payments: (params: Params) => get<Paginated<Payment>>('/payments/', params),
  previewPayment: (body: { profile: number; amount: string; mode: PaymentTarget; invoice?: number | null }) =>
    post<PaymentPreview>('/payments/preview/', body),
  /** Ключ живёт, пока открыта форма: повторная отправка возвращает тот же платёж. */
  recordPayment: (body: PaymentBody, idempotencyKey: string) =>
    post<Payment>('/payments/', body, { 'Idempotency-Key': idempotencyKey }),
  reversePayment: (id: number, reason: string) => post<Payment>(`/payments/${id}/reverse/`, { reason }),
  payment: (id: number) => get<Payment>(`/payments/${id}/`),
  /** Исправить проведённый платёж (причина обязательна; повтор той же формы ничего не меняет). */
  correctPayment: (id: number, body: PaymentCorrection) => post<PaymentCorrectionResult>(`/payments/${id}/correct/`, body),
  correctCreatedAt: (id: number, body: { created_at: string; reason: string }) =>
    post<Payment>(`/payments/${id}/created-at/`, body),
  paymentHistory: (id: number) => get<AuditEntry[]>(`/payments/${id}/history/`),
  refundPayment: (id: number, amount: string, reason: string, idempotencyKey: string) =>
    post<Payment>(`/payments/${id}/refund/`, { amount, reason }, { 'Idempotency-Key': idempotencyKey }),
  payReservation: (id: number, body: { amount: string; received_date: string; method: string; payer_name?: string },
    idempotencyKey: string) => post(`/reservations/${id}/pay/`, body, { 'Idempotency-Key': idempotencyKey }),
  editReservation: (id: number, body: { expected_amount?: string; reserved_until?: string | null; reason: string }) =>
    post(`/reservations/${id}/edit/`, body),
  cancelReservation: (id: number, reason: string) => post(`/reservations/${id}/cancel/`, { reason }),
  receipts: (params: Params) => get<Paginated<Receipt>>('/receipts/', params),
  receipt: (id: number) => get<Receipt>(`/receipts/${id}/`),
  receiptPrinted: (id: number) => post<Receipt>(`/receipts/${id}/printed/`),
  openReceiptPdf: (id: number, size: 'a4' | 'compact' = 'a4') => receiptPdf(id, size, 'open'),
  downloadReceiptPdf: (id: number, size: 'a4' | 'compact' = 'a4') => receiptPdf(id, size, 'download'),
  addContact: (body: { profile: number; channel: string; result: string; comment?: string;
    promised_payment_date?: string | null; next_contact_date?: string | null }) => post('/contacts/', body),
  analytics: (params: Params) => get<Analytics>('/analytics/', params),
  plans: () => get<Paginated<Plan>>('/plans/', { page_size: 200 }),
  createPlan: (body: PlanBody) => post<Plan>('/plans/', { ...body, reason: 'Новая программа' }),
  updatePlan: (id: number, body: Partial<PlanBody> & { is_active?: boolean }) => patch<Plan>(`/plans/${id}/`, body),
  addPlanPrice: (id: number, body: { lessons_per_package: number; package_price: string; effective_from: string; reason: string }) =>
    post(`/plans/${id}/versions/`, body),
  audit: (params: Params) => get<Paginated<AuditRow>>('/audit-log/', params),
  settings: () => get<FinanceSettings>('/settings/'),
  updateSettings: (body: Partial<FinanceSettings>) => patch<FinanceSettings>('/settings/', body),
}
