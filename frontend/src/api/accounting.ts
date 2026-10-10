import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  AccountingOptions,
  AuditEntry,
  CalculationResult,
  Capabilities,
  Dashboard,
  EmployeeRow,
  PayrollAdjustment,
  PayrollDetail,
  PayrollListItem,
  PayrollPayment,
  PayrollPeriod,
  PeriodSelection,
  PeriodType,
  SalaryProfile,
  SalaryRule,
  StudentPayment,
  StudentRef,
} from '@/types/accounting'

const BASE = '/accounting'

type Params = Record<string, string | number | boolean | undefined | null>

const get = <T>(url: string, params?: Params) => apiClient.get<T>(`${BASE}${url}`, { params }).then((r) => r.data)
const post = <T>(url: string, body?: unknown, headers?: Record<string, string>) =>
  apiClient.post<T>(`${BASE}${url}`, body, { headers }).then((r) => r.data)

/** Query params for a period choice: one half → period_type; whole month → none. */
export function periodParams(selection: PeriodSelection): Params {
  return {
    year: selection.year,
    month: selection.month,
    period_type: selection.half === 'MONTH' ? undefined : selection.half,
  }
}

/** A fresh key per submitted form: the backend returns the same payment
 * for a repeated request instead of creating a second one. */
export function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** Files are behind JWT like every call — a plain `<a href>` would 401 — so they are fetched as a blob. */
async function download(url: string, params: Params | undefined, fallbackName: string): Promise<void> {
  const response = await apiClient.get<Blob>(`${BASE}${url}`, { params, responseType: 'blob' })
  const match = /filename="?([^";]+)"?/.exec(String(response.headers['content-disposition'] ?? ''))
  const href = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = href
  link.download = match?.[1] ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

export interface PayrollFilters {
  search?: string
  salary_type?: string
  program?: number
  group?: number
  status?: string
  employee?: number
}

export const accountingApi = {
  me: () => get<Capabilities>('/me/'),
  options: () => get<AccountingOptions>('/options/'),
  dashboard: (selection: PeriodSelection) => get<Dashboard>('/dashboard/', periodParams(selection)),
  employees: (selection: PeriodSelection, filters: PayrollFilters & { payment_status?: string } = {}) =>
    get<{ range_label: string; results: EmployeeRow[] }>('/employees/', { ...periodParams(selection), ...filters }),
  students: (search: string) => get<StudentRef[]>('/students/', { search }),

  periods: (params?: Params) => get<Paginated<PayrollPeriod>>('/periods/', params),
  ensurePeriod: (year: number, month: number, periodType: PeriodType) =>
    post<PayrollPeriod>('/periods/', { year, month, period_type: periodType }),
  calculatePeriod: (id: number) => post<CalculationResult>(`/periods/${id}/calculate/`),
  approvePeriod: (id: number) =>
    post<{ approved: number[]; failed: { payroll_id: number; employee: string; error: string }[]; period: PayrollPeriod }>(
      `/periods/${id}/approve/`,
    ),
  closePeriod: (id: number, reason = '') => post<PayrollPeriod>(`/periods/${id}/close/`, { reason }),

  payrolls: (params: Params) => get<Paginated<PayrollListItem>>('/payrolls/', params),
  payroll: (id: number) => get<PayrollDetail>(`/payrolls/${id}/`),
  recalculate: (id: number) => post<PayrollDetail>(`/payrolls/${id}/recalculate/`),
  approve: (id: number) => post<PayrollDetail>(`/payrolls/${id}/approve/`),
  returnForFix: (id: number, reason: string) => post<PayrollDetail>(`/payrolls/${id}/return/`, { reason }),
  reopen: (id: number, reason: string) => post<PayrollDetail>(`/payrolls/${id}/reopen/`, { reason }),
  voidPayroll: (id: number, reason: string) => post<PayrollDetail>(`/payrolls/${id}/void/`, { reason }),
  registerPayment: (
    id: number,
    body: { amount: string; payment_date: string; payment_method: string; reference: string; comment: string; is_advance: boolean },
    idempotencyKey: string,
  ) => post<PayrollPayment>(`/payrolls/${id}/payments/`, body, { 'Idempotency-Key': idempotencyKey }),
  voidPayment: (id: number, reason: string) => post<PayrollPayment>(`/payments/${id}/void/`, { reason }),
  addAdjustment: (id: number, body: { kind: string; amount: string; reason: string }) =>
    post<PayrollAdjustment>(`/payrolls/${id}/adjustments/`, body),
  decideAdjustment: (id: number, approve: boolean, reason = '') =>
    post<PayrollAdjustment>(`/adjustments/${id}/decide/`, { approve, reason }),
  voidAdjustment: (id: number, reason: string) => post<PayrollAdjustment>(`/adjustments/${id}/void/`, { reason }),
  downloadPayrollPdf: (id: number) => download(`/payrolls/${id}/report.pdf/`, undefined, `payroll-${id}.pdf`),
  downloadPayrollXlsx: (id: number) => download(`/payrolls/${id}/report.xlsx/`, undefined, `payroll-${id}.xlsx`),
  downloadReport: (format: 'pdf' | 'xlsx', selection: PeriodSelection, filters: PayrollFilters = {}) =>
    download(`/reports/payroll.${format}`, { ...periodParams(selection), ...filters }, `payroll.${format}`),

  profiles: (params?: Params) => get<Paginated<SalaryProfile>>('/salary-profiles/', { page_size: 200, ...params }),
  createProfile: (body: { employee: number; salary_type: string; position: string; effective_from: string }) =>
    post<SalaryProfile>('/salary-profiles/', body),
  updateProfile: (id: number, body: Partial<{ salary_type: string; position: string; is_active: boolean; effective_to: string | null }>) =>
    apiClient.patch<SalaryProfile>(`${BASE}/salary-profiles/${id}/`, body).then((r) => r.data),
  createRule: (body: Record<string, unknown>) => post<SalaryRule>('/salary-rules/', body),
  newRuleVersion: (id: number, body: Record<string, unknown>) => post<SalaryRule>(`/salary-rules/${id}/new-version/`, body),
  deactivateRule: (id: number, effectiveTo: string, reason: string) =>
    post<SalaryRule>(`/salary-rules/${id}/deactivate/`, { effective_to: effectiveTo, reason }),

  studentPayments: (params: Params) => get<Paginated<StudentPayment>>('/student-payments/', params),
  createStudentPayment: (body: Record<string, unknown>, idempotencyKey: string) =>
    post<StudentPayment>('/student-payments/', body, { 'Idempotency-Key': idempotencyKey }),
  voidStudentPayment: (id: number, reason: string) => post<StudentPayment>(`/student-payments/${id}/void/`, { reason }),

  audit: (params: Params) => get<Paginated<AuditEntry>>('/audit-log/', params),

  myPayrolls: () => get<Paginated<PayrollDetail>>('/my/payrolls/'),
  downloadMyPayrollPdf: (id: number) => download(`/my/payrolls/${id}/report.pdf/`, undefined, `payroll-${id}.pdf`),
}
