import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  AccountingOptions,
  AnalyticsFilters,
  AnalyticsSummary,
  AuditEntry,
  BlockEstimate,
  CoursePriceVersion,
  CycleAccrual,
  DeductionEffects,
  Earnings,
  EarningsRow,
  PayoutScheduleResponse,
  DeductionRule,
  DeductionRuleBody,
  DepartmentTotals,
  MyEstimate,
  TeacherReport,
  CalculationResult,
  Capabilities,
  CourseCycle,
  CourseSettings,
  MySalary,
  MySalaryFilters,
  MyPlannedPayout,
  PayoutCalendar,
  PayoutCandidate,
  PayoutPlan,
  PayoutPlanCreateBody,
  PayoutPlanDetail,
  PayoutPlanFilters,
  PayoutPlanSummary,
  Dashboard,
  EmployeeRow,
  CashFlowResponse,
  Expense,
  ExpenseBody,
  ExpenseCategory,
  ExpenseFilters,
  ExpenseList,
  ExpenseOptions,
  ExpenseReport,
  FinanceOverview,
  FinanceRange,
  RecurringExpense,
  PayrollAdjustment,
  PayrollDetail,
  PayrollListItem,
  PayrollPayment,
  PayrollPeriod,
  PeriodSelection,
  PeriodType,
  RuleChangeBody,
  RuleChangeEffects,
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
const patch = <T>(url: string, body: unknown) => apiClient.patch<T>(`${BASE}${url}`, body).then((r) => r.data)

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
  createProfile: (body: { employee: number; salary_type: string; position: string; effective_from: string; department?: string }) =>
    post<SalaryProfile>('/salary-profiles/', body),
  updateProfile: (id: number, body: Partial<{ salary_type: string; position: string; is_active: boolean; effective_to: string | null; department: string }>) =>
    apiClient.patch<SalaryProfile>(`${BASE}/salary-profiles/${id}/`, body).then((r) => r.data),
  createRule: (body: Record<string, unknown>) => post<SalaryRule>('/salary-rules/', body),
  newRuleVersion: (id: number, body: Record<string, unknown>) => post<SalaryRule>(`/salary-rules/${id}/new-version/`, body),
  /** Исправить ошибочное правило на месте (пока оно не в утверждённых начислениях). */
  correctRule: (id: number, body: RuleChangeBody) =>
    post<{ rule: SalaryRule; effects: RuleChangeEffects }>(`/salary-rules/${id}/correct/`, body),
  /** Заменить правило с даты: старое закрывается днём раньше, история не меняется. */
  replaceRule: (id: number, body: RuleChangeBody & { effective_from: string }) =>
    post<{ rule: SalaryRule; effects: RuleChangeEffects }>(`/salary-rules/${id}/replace/`, body),
  deactivateRule: (id: number, effectiveTo: string, reason: string) =>
    post<SalaryRule>(`/salary-rules/${id}/deactivate/`, { effective_to: effectiveTo, reason }),

  studentPayments: (params: Params) => get<Paginated<StudentPayment>>('/student-payments/', params),
  createStudentPayment: (body: Record<string, unknown>, idempotencyKey: string) =>
    post<StudentPayment>('/student-payments/', body, { 'Idempotency-Key': idempotencyKey }),
  voidStudentPayment: (id: number, reason: string) => post<StudentPayment>(`/student-payments/${id}/void/`, { reason }),

  courseSettings: () => get<Paginated<CourseSettings>>('/course-settings/', { page_size: 200 }),
  createCourseSettings: (body: Record<string, unknown>) => post<CourseSettings>('/course-settings/', body),
  updateCourseSettings: (id: number, body: Record<string, unknown>) =>
    apiClient.patch<CourseSettings>(`${BASE}/course-settings/${id}/`, body).then((r) => r.data),
  cycles: (params: Params) => get<Paginated<CourseCycle>>('/cycles/', { page_size: 200, ...params }),

  audit: (params: Params) => get<Paginated<AuditEntry>>('/audit-log/', params),

  /** История тарифов: новая версия — с датой начала и причиной; старые не меняются. */
  pricing: (params: Params = {}) => get<Paginated<CoursePriceVersion>>('/pricing/', { page_size: 200, ...params }),
  createPrice: (body: { course: number; price_per_student: string; effective_from: string; reason: string }) =>
    post<CoursePriceVersion>('/pricing/', body),
  cycleAccruals: (params: Params) => get<Paginated<CycleAccrual>>('/cycle-accruals/', params),
  reviewCycleAccrual: (id: number, confirm: boolean, reason: string) =>
    post<CycleAccrual>(`/cycle-accruals/${id}/review/`, { confirm, reason }),
  estimates: (params: Params = {}) => get<Paginated<BlockEstimate>>('/estimates/', params),

  analyticsSummary: (filters: AnalyticsFilters) => get<AnalyticsSummary>('/analytics/summary/', { ...filters }),
  analyticsByDepartment: (filters: AnalyticsFilters) =>
    get<{ year: number; month: number; results: DepartmentTotals[] }>('/analytics/by-department/', { ...filters }),
  teacherReport: (filters: AnalyticsFilters & { page?: number; page_size?: number }) =>
    get<TeacherReport>('/reports/teachers/', { ...filters }),
  downloadTeacherReport: (format: 'pdf' | 'xlsx', filters: AnalyticsFilters) =>
    download(`/reports/teachers.${format}`, { ...filters }, `teachers.${format}`),

  /** Заработано на текущий момент: по проведённым урокам и правилам; ничего не начисляет. */
  earnings: (params: Params = {}) => get<Paginated<EarningsRow>>('/earnings/', { page_size: 200, ...params }),
  payoutSchedule: (params: Params = {}) => get<PayoutScheduleResponse>('/earnings/schedule/', params),
  employeeEarnings: (employeeId: number) => get<Earnings & { employee: number; employee_name: string }>(`/earnings/${employeeId}/`),

  /** Налоги и удержания: правило не удаляется; изменение — с причиной (новая версия, если уже утверждено). */
  deductionRules: (params: Params = {}) => get<Paginated<DeductionRule>>('/deduction-rules/', { page_size: 200, ...params }),
  createDeductionRule: (body: DeductionRuleBody) =>
    post<{ rule: DeductionRule; effects: DeductionEffects }>('/deduction-rules/', body),
  changeDeductionRule: (id: number, body: Partial<DeductionRuleBody> & { reason: string }) =>
    post<{ rule: DeductionRule; effects: DeductionEffects }>(`/deduction-rules/${id}/change/`, body),
  deductionRuleHistory: (id: number) =>
    get<{ versions: DeductionRule[]; audit: AuditEntry[] }>(`/deduction-rules/${id}/history/`),

  /** План выплат. Подготовленные средства — не выплаты; фактическая выплата —
   * `payPlanLine` (тот же механизм выплат, что и в карточке начисления). */
  payoutPlans: (filters: PayoutPlanFilters) => get<Paginated<PayoutPlan>>('/payout-plans/', { ...filters }),
  payoutPlan: (id: number) => get<PayoutPlanDetail>(`/payout-plans/${id}/`),
  payoutSummary: (filters: PayoutPlanFilters) => get<PayoutPlanSummary>('/payout-plans/summary/', { ...filters, page: undefined }),
  payoutCalendar: (filters: PayoutPlanFilters) => get<PayoutCalendar>('/payout-plans/calendar/', { ...filters, page: undefined }),
  payoutCandidates: (params: { year?: number; month?: number; employee?: number; department?: string }) =>
    get<{ results: PayoutCandidate[] }>('/payout-plans/candidates/', params),
  createPayoutPlan: (body: PayoutPlanCreateBody) => post<PayoutPlanDetail>('/payout-plans/', body),
  updatePayoutPlan: (id: number, body: Record<string, unknown> & { version: number }) =>
    patch<PayoutPlanDetail>(`/payout-plans/${id}/`, body),
  approvePayoutPlan: (id: number, version: number) => post<PayoutPlanDetail>(`/payout-plans/${id}/approve/`, { version }),
  cancelPayoutPlan: (id: number, version: number, reason: string) =>
    post<PayoutPlanDetail>(`/payout-plans/${id}/cancel/`, { version, reason }),
  addPayoutLines: (id: number, version: number, lines: { payroll: number; amount?: string | null }[]) =>
    post<PayoutPlanDetail>(`/payout-plans/${id}/lines/`, { version, lines }),
  updatePayoutLine: (id: number, lineId: number, body: { version: number; amount?: string; comment?: string; remove?: boolean; reason?: string }) =>
    patch<PayoutPlanDetail>(`/payout-plans/${id}/lines/${lineId}/`, body),
  payPlanLine: (
    id: number, lineId: number,
    body: { amount: string; payment_date: string; payment_method: string; reference: string; comment: string },
    idempotencyKey: string,
  ) => post<PayrollPayment>(`/payout-plans/${id}/lines/${lineId}/pay/`, body, { 'Idempotency-Key': idempotencyKey }),
  downloadPayoutPlan: (id: number, format: 'pdf' | 'xlsx') =>
    download(`/payout-plans/${id}/report.${format}/`, undefined, `payout-plan-${id}.${format}`),
  myPayoutPlan: () => get<{ results: MyPlannedPayout[] }>('/my/payout-plan/'),

  /** Расходы компании. Неоплаченный расход — обязательство, не потраченные
   * деньги; оплата — `payExpense`; удаления нет — только отмена с причиной. */
  expenseOptions: () => get<ExpenseOptions>('/expenses/options/'),
  expenses: (filters: ExpenseFilters) => get<ExpenseList>('/expenses/', { ...filters }),
  expense: (id: number) => get<Expense>(`/expenses/${id}/`),
  /** Документ в той же форме (multipart), если он выбран. */
  createExpense: (body: ExpenseBody & { paid?: boolean; paid_date?: string | null; document?: File | null }, idempotencyKey: string) => {
    const { document, ...rest } = body
    if (!document) return post<Expense>('/expenses/', rest, { 'Idempotency-Key': idempotencyKey })
    const form = new FormData()
    for (const [key, value] of Object.entries(rest)) {
      if (value !== undefined && value !== null) form.append(key, String(value))
    }
    form.append('document', document)
    return post<Expense>('/expenses/', form, { 'Idempotency-Key': idempotencyKey })
  },
  updateExpense: (id: number, body: Partial<ExpenseBody> & { version: number; reason?: string }) =>
    patch<Expense>(`/expenses/${id}/`, body),
  payExpense: (id: number, body: { paid_date: string; payment_method?: string; reference?: string; version: number }) =>
    post<Expense>(`/expenses/${id}/pay/`, body),
  unpayExpense: (id: number, reason: string, version: number) => post<Expense>(`/expenses/${id}/unpay/`, { reason, version }),
  voidExpense: (id: number, reason: string, version: number) => post<Expense>(`/expenses/${id}/void/`, { reason, version }),
  expenseHistory: (id: number) => get<{ results: AuditEntry[] }>(`/expenses/${id}/history/`),
  uploadExpenseDocument: (id: number, file: File, version: number) => {
    const form = new FormData()
    form.append('document', file)
    form.append('version', String(version))
    return post<Expense>(`/expenses/${id}/document/`, form)
  },
  downloadExpenseDocument: (id: number, name: string) => download(`/expenses/${id}/document/`, undefined, name || `expense-${id}`),
  expenseReport: (range: FinanceRange, filters: ExpenseFilters = {}) =>
    get<ExpenseReport>('/expenses/report/', { ...filters, ...range, page: undefined }),
  downloadExpenses: (range: FinanceRange, filters: ExpenseFilters = {}) =>
    download('/expenses/export.xlsx/', { ...filters, ...range, page: undefined }, 'expenses.xlsx'),
  expenseCategories: () => get<ExpenseCategory[]>('/expense-categories/'),
  createExpenseCategory: (body: { name: string; description?: string; sort_order?: number }) =>
    post<ExpenseCategory>('/expense-categories/', body),
  updateExpenseCategory: (id: number, body: Partial<Pick<ExpenseCategory, 'name' | 'description' | 'sort_order' | 'is_active'>>) =>
    patch<ExpenseCategory>(`/expense-categories/${id}/`, body),
  recurringExpenses: () => get<RecurringExpense[]>('/recurring-expenses/'),
  createRecurringExpense: (body: Record<string, unknown>) => post<RecurringExpense>('/recurring-expenses/', body),
  updateRecurringExpense: (id: number, body: Record<string, unknown>) => patch<RecurringExpense>(`/recurring-expenses/${id}/`, body),
  generateRecurringExpenses: (year: number, month: number) =>
    post<{ year: number; month: number; created: number[]; skipped: number[] }>('/recurring-expenses/generate/', { year, month }),

  /** Единая финансовая панель, касса (движение денег) и общий отчёт Excel. */
  financeOverview: (range: FinanceRange) => get<FinanceOverview>('/finance/overview/', { ...range }),
  cashFlow: (range: FinanceRange, params: Params = {}) => get<CashFlowResponse>('/finance/cash-flow/', { ...range, ...params }),
  downloadFinanceReport: (range: FinanceRange) => download('/finance/report.xlsx', { ...range }, 'finance.xlsx'),

  /** Сотрудник — всегда текущий пользователь на сервере; id в запросе нет. */
  mySalary: (filters: MySalaryFilters = {}) => get<MySalary>('/my/salary/', { ...filters }),
  downloadMySalaryPdf: (filters: MySalaryFilters = {}) => download('/my/salary/report.pdf', { ...filters }, 'my-salary.pdf'),
  myPayrolls: () => get<Paginated<PayrollDetail>>('/my/payrolls/'),
  myEstimates: () => get<{ results: MyEstimate[]; note: string }>('/my/estimates/'),
  downloadMyPayrollPdf: (id: number) => download(`/my/payrolls/${id}/report.pdf/`, undefined, `payroll-${id}.pdf`),
}
