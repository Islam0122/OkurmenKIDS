/** Бухгалтерия (backend: apps.accounting, /api/v1/accounting/). Все суммы —
 * строки Decimal в сомах (KGS), как их отдаёт DRF: без потерь float. */

/** Половины месяца — для процента от курса; MONTH — оклад за полный месяц. */
export type PeriodType = 'FIRST_HALF' | 'SECOND_HALF' | 'MONTH'
export type PeriodStatus = 'DRAFT' | 'CALCULATED' | 'APPROVED' | 'CLOSED'
export type PayrollStatus = 'DRAFT' | 'CALCULATED' | 'RETURNED' | 'APPROVED' | 'PARTIALLY_PAID' | 'PAID' | 'VOID'
/** Только два типа оплаты: оклад и процент от стоимости курса. Прочие
 * значения — устаревшие записи первой версии (только для истории). */
export type SalaryType = 'FIXED' | 'PERCENT' | (string & {})
export type RuleType = 'FIXED' | 'PERCENT'
export type Department = 'IT' | 'SOFT_SKILLS' | 'ENGLISH' | 'TEAM_LEAD' | 'ASSISTANT' | 'OTHER'
export type CycleAccrualStatus = 'ACCRUED' | 'APPROVED' | 'CANCELLED' | 'CORRECTED' | 'CORRECTION_REQUIRED' | 'REVIEW_REQUIRED'
export type EstimateStatus = 'ESTIMATED' | 'BLOCK_IN_PROGRESS' | 'READY_FOR_ACCRUAL'
export type AdjustmentKind = 'BONUS' | 'DEDUCTION' | 'CORRECTION'

export interface Choice {
  value: string
  label: string
}

export interface Capabilities {
  can_view: boolean
  can_operate: boolean
  can_approve: boolean
}

export interface AccountingOptions extends Capabilities {
  employees: { id: number; full_name: string; role: string }[]
  courses: { id: number; name: string }[]
  groups: { id: number; name: string; course: number; status: string }[]
  salary_types: Choice[]
  rule_types: Choice[]
  methods: Record<RuleType, Choice[]>
  student_count_rules: Choice[]
  payment_methods: Choice[]
  student_payment_methods: Choice[]
  adjustment_kinds: Choice[]
  payroll_statuses: Choice[]
  departments: Choice[]
  subjects: { id: number; name: string }[]
  trainer_split_rules: Choice[]
  trainers: { id: number; name: string }[]
}

export interface PayrollPeriod {
  id: number
  year: number
  month: number
  period_type: PeriodType
  period_type_display: string
  start_date: string
  end_date: string
  status: PeriodStatus
  status_display: string
  label: string
  created_at: string
  approved_at: string | null
}

export interface Dashboard {
  total_accrued: string
  total_lines: string
  total_adjustments: string
  /** Удержания по правилам «Налоги и удержания» за выбранный период. */
  total_deductions: string
  total_paid: string
  total_due: string
  employees_with_accruals: number
  pending_approval: number
  pending_adjustments: number
  with_errors: number
  outstanding_debt_all_periods: string
  open_cycles: number
  range_label: string
  periods: PayrollPeriod[]
}

export interface EmployeeRow {
  profile_id: number
  employee: number
  employee_name: string
  position: string
  salary_type: SalaryType
  salary_type_display: string
  department: Department
  department_display: string
  /** Где считается: оклад — месячный период, процент — половины месяца. */
  calc_period: 'MONTH' | 'HALF'
  is_active: boolean
  rates: { rule_type: string; label: string; amount: string | null; percentage: string | null; scope: string }[]
  active_students: number | null
  payroll_id: number | null
  accrued: string | null
  paid: string | null
  due: string | null
  status: PayrollStatus | 'MIXED' | null
  status_display: string | null
}

export interface PayrollLine {
  id: number
  line_type: string
  line_type_display: string
  description: string
  source_type: string
  source_id: number | null
  salary_rule: number | null
  quantity: string | null
  rate: string | null
  percentage: string | null
  base_amount: string | null
  amount: string
  metadata: {
    payments?: { id: number; student: string; amount: string; counted: string; received_date: string; service_start: string; service_end: string }[]
    lessons?: number
    completed_on?: string
    late?: boolean
    /** Активные студенты — только агрегатом (поимённого списка API не отдаёт). */
    students_count?: number
    student_days?: number
    [key: string]: unknown
  }
}

export interface PayrollPayment {
  id: number
  payroll: number
  amount: string
  payment_date: string
  payment_method: string
  payment_method_display: string
  reference: string
  comment: string
  is_advance: boolean
  status: 'CONFIRMED' | 'VOID'
  status_display: string
  void_reason: string
  created_by_name: string
  created_at: string
  voided_at: string | null
}

export interface PayrollAdjustment {
  id: number
  payroll: number
  kind: AdjustmentKind
  kind_display: string
  amount: string
  reason: string
  status: 'PENDING' | 'APPLIED' | 'REJECTED' | 'VOID'
  status_display: string
  created_by_name: string
  decided_by_name: string
  decided_at: string | null
  created_at: string
}

export interface AuditEntry {
  id: number
  actor: number | null
  actor_name: string
  entity_type: string
  entity_id: number
  action: string
  old_values: Record<string, unknown>
  new_values: Record<string, unknown>
  reason: string
  payroll: number | null
  created_at: string
}

export interface SalaryRule {
  id: number
  employee_profile: number
  employee: number
  employee_name: string
  rule_type: RuleType | (string & {})
  rule_type_display: string
  amount: string | null
  percentage: string | null
  program: number | null
  program_name: string | null
  group: number | null
  group_name: string | null
  calculation_method: string
  calculation_method_display: string
  first_half_share: string
  description: string
  effective_from: string
  effective_to: string | null
  is_active: boolean
  previous_version: number | null
  next_version: number | null
  /** Где правило уже использовано: исправить на месте можно, только пока нет утверждённых начислений. */
  usage: RuleUsage
  created_at: string
}

export interface RuleUsage {
  can_correct: boolean
  locked_payrolls: number
  draft_payrolls: number
  locked_accruals: number
  open_accruals: number
  /** Последняя дата, по которую правило использовано в утверждённых начислениях. */
  used_until: string | null
}

/** Что пересчитано после исправления или замены правила. */
export interface RuleChangeEffects {
  accruals_updated: number
  accruals_cancelled: number
  payrolls_recalculated: number[]
  payrolls_voided: number[]
  payrolls_failed: { payroll_id: number; error: string }[]
}

export interface RuleChangeBody {
  rule_type?: RuleType
  amount?: string | null
  percentage?: string | null
  program?: number | null
  group?: number | null
  description?: string
  effective_from?: string
  effective_to?: string | null
  reason: string
}

export interface SalaryProfile {
  id: number
  employee: number
  employee_name: string
  employee_role: string
  position: string
  display_position: string
  salary_type: SalaryType
  salary_type_display: string
  /** Пусто — направление по роли (см. effective_department). */
  department: Department | ''
  effective_department: Department
  department_display: string
  currency: string
  is_active: boolean
  effective_from: string
  effective_to: string | null
  rules: SalaryRule[]
}

export interface PayrollListItem {
  id: number
  period: number
  period_label: string
  period_type: PeriodType
  employee: number
  employee_name: string
  position: string
  salary_type: SalaryType | ''
  salary_type_display: string
  department: Department | ''
  department_display: string
  status: PayrollStatus
  status_display: string
  active_students: number | null
  /** Плановая дата выплаты — не факт перевода. null — календарь не настроен. */
  planned_payment_date: string | null
  total_accrued: string
  total_adjustments: string
  total_deductions: string
  total: string
  total_paid: string
  amount_due: string
  warnings: string[]
  errors: string[]
  has_errors: boolean
  calculated_at: string | null
  approved_at: string | null
}

export interface PayrollDetail extends PayrollListItem {
  lines: PayrollLine[]
  payments: PayrollPayment[]
  adjustments: PayrollAdjustment[]
  approved_by_name: string
  period_detail: PayrollPeriod
  rules: SalaryRule[]
  audit?: AuditEntry[]
  return_reason: string
  /** Незавершённые циклы групп сотрудника — процент за них ещё не начисляется. */
  open_cycles: { id: number; group_name: string; course_name: string; number: number; lessons_done: number; required_lessons: number }[]
  deductions: PayrollDeduction[]
}

/** Удержание месяца в детализации расчёта: за месяц полагается `month_amount`,
 * из этого расчёта взято `amount`, из других расчётов месяца — `other_payrolls`. */
export interface PayrollDeduction {
  id: number
  rule: number
  name: string
  kind: DeductionKind
  kind_display: string
  frequency_display: string
  year: number
  month: number
  month_amount: string
  amount: string
  other_payrolls: string
  remaining: string
}

export interface CalculationResult {
  period: PayrollPeriod
  calculated: PayrollListItem[]
  skipped: { employee_id: number; employee: string; payroll_id: number; status: string; reason: string }[]
  failed: { employee_id: number; employee: string; error: string }[]
}

export interface StudentPayment {
  id: number
  student: number
  student_name: string
  group: number
  group_name: string
  course: number
  course_name: string
  kind: 'payment' | 'refund'
  kind_display: string
  amount: string
  currency: string
  received_date: string
  service_start: string
  service_end: string
  refund_of: number | null
  refunded_amount: string | null
  method: string
  method_display: string
  reference: string
  comment: string
  status: 'confirmed' | 'void'
  status_display: string
  void_reason: string
  created_by_name: string
  created_at: string
  voided_at: string | null
  affected_payrolls?: number[]
}

export interface StudentRef {
  id: number
  name: string
  group: number | null
  group_name: string | null
  status: string
}

/** Выбор периода в интерфейсе: половина месяца или полный месяц. */
export interface PeriodSelection {
  year: number
  month: number
  half: PeriodType | 'MONTH'
}

export interface CourseSettings {
  id: number
  course: number
  course_name: string
  course_count_lesson: number
  /** Цена первой версии тарифа (меняется только через историю тарифов). */
  price_per_student: string
  /** Тариф, действующий сегодня. */
  current_price: string | null
  counted_subjects: number[]
  counted_subjects_names: string[]
  trainer_split_rule: 'BY_LESSONS' | 'REVIEW'
  trainer_split_rule_display: string
  required_lessons: number
  /** Необязательно: пусто — учёт с первого проведённого урока. */
  count_lessons_from: string | null
  student_count_rule: string
  student_count_rule_display: string
  is_active: boolean
  updated_at: string
}

export interface CycleAccrualRef {
  id: number
  employee: number
  employee_name: string
  percentage: string
  amount: string
  /** Уроков цикла, проведённых сотрудником; null — весь цикл (до предметного учёта или привязка к группе). */
  lessons_taught: number | null
  share: string
  status: CycleAccrualStatus
  status_display: string
  note: string
  payroll: number | null
  payroll_status: PayrollStatus | null
  payroll_status_display: string | null
  period_label: string | null
  adjustment: number | null
  review_reasons: string[]
  planned_payment_date: string
}

/** Цикл ПРЕДМЕТА группы: у IT, English, Soft Skills свои циклы и прогресс. */
export interface CourseCycle {
  id: number
  group: number
  group_name: string
  course: number
  course_name: string
  subject: number | null
  subject_name: string
  /** false — исторический общий цикл группы (до предметного учёта). */
  per_subject: boolean
  number: number
  status: 'IN_PROGRESS' | 'COMPLETED' | 'INVALIDATED'
  status_display: string
  required_lessons: number
  lessons_done: number
  lessons_remaining: number
  progress_percent: number
  /** Порог: накопленные проведённые уроки предмета (12, 24, 36…). */
  lessons_total: number
  /** Уроков предмета в учебном плане курса (например, 48). */
  subject_plan_lessons: number | null
  invalidated_reason: string
  start_date: string | null
  completed_on: string | null
  student_count: number | null
  course_price: string | null
  base_amount: string | null
  trainers: string[]
  trainer_lessons: { teacher: number; name: string; lessons: number }[]
  warnings: string[]
  lessons_linked: number
  accruals: CycleAccrualRef[]
}

/** «Моя зарплата» — /accounting/my/salary/ (только свои данные, только чтение). */
export type MySalaryStatus = 'AWAITING' | 'CALCULATED' | 'APPROVED' | 'PARTIALLY_PAID' | 'PAID'

export interface MySalaryRow {
  payroll_id: number | null
  year: number
  month: number
  period_type: PeriodType
  period_label: string
  status: MySalaryStatus
  status_display: string
  is_final: boolean
  /** null — суммы ещё не рассчитаны («Ожидает расчёта»). */
  accrued: string | null
  paid: string | null
  due: string | null
  lines: { description: string; amount: string }[]
  adjustments: { kind: string; reason: string; amount: string }[]
  deducted: string | null
  deductions: { name: string; kind_display: string; amount: string; month_amount: string; remaining: string }[]
  planned_payment_date: string | null
}

export interface MySalary {
  employee_name: string
  has_profile: boolean
  profile: {
    salary_type: SalaryType
    salary_type_display: string
    position: string
    rates: { rule_type: string; label: string; amount: string | null; percentage: string | null; scope: string; effective_from: string }[]
  } | null
  /** Итоги по утверждённым начислениям — считает backend: до удержаний, удержания,
   * после удержаний, выплачено, остаток (= Σ остатков расчётов). */
  totals: {
    accrued: string
    deducted: string
    net: string
    paid: string
    due: string
    pending_approval: string
    estimated: string
    /** Удержание для предварительной суммы не прогнозируется — null и пояснение. */
    estimated_deductions: string | null
    estimated_deductions_note: string
  }
  deductions: MyDeduction[]
  /** Заработано на текущий момент — тот же расчёт, что у бухгалтера. */
  earnings: Earnings
  next_planned_payment_date: string | null
  estimates: MyEstimate[]
  last_payment: { payment_date: string; amount: string } | null
  current_month: { year: number; month: number; label: string; accrued: string; periods: MySalaryRow[] }
  history: MySalaryRow[]
  payments: { id: number; payment_date: string; amount: string; method: string; is_advance: boolean; reference: string; period_label: string; payroll_id: number }[]
  filters: { year: number | null; month: number | null; period_type: PeriodType | null }
}

export interface MySalaryFilters {
  year?: number
  month?: number
  period_type?: PeriodType
}

/** Предварительная зарплата по незавершённому блоку — не начисление и не долг. */
export interface MyEstimate {
  cycle_id: number
  cycle_number: number
  group_name: string
  course_name: string
  subjects: string[]
  subject_name: string
  /** «11 из 12 уроков» — ожидаемая доля тренера в блоке предмета. */
  share_label: string
  student_count: number
  price_per_student: string
  percentage: string
  expected_amount: string
  lessons_done: number
  required_lessons: number
  lessons_remaining: number
  projected_completion_date: string | null
  expected_payment_date: string | null
  status: EstimateStatus
  status_display: string
  warnings: string[]
  note: string
}

/** Оценка блока в бухгалтерии: те же параметры + сотрудник. */
export interface BlockEstimate extends Omit<MyEstimate, 'percentage' | 'expected_amount'> {
  subject: number | null
  trainers: { name: string; lessons: number }[]
  expected_lessons: number | null
  employee: number | null
  employee_name: string
  group: number
  course: number
  percentage: string | null
  expected_amount: string | null
  base_amount: string
  student_count_rule_display: string
}

export interface CoursePriceVersion {
  id: number
  course: number
  course_name: string
  price_per_student: string
  currency: string
  effective_from: string
  effective_to: string | null
  reason: string
  previous_version: number | null
  is_migrated: boolean
  is_current: boolean
  created_by: number | null
  created_by_name: string
  created_at: string
}

export interface CycleAccrual {
  id: number
  cycle: number
  cycle_number: number
  group: number
  group_name: string
  course_name: string
  subject_name: string
  employee: number
  employee_name: string
  status: CycleAccrualStatus
  status_display: string
  lessons: number
  lessons_taught: number | null
  share: string
  lessons_total: number
  completed_on: string
  student_count: number
  course_price: string
  percentage: string
  amount: string
  planned_payment_date: string
  payroll: number | null
  review_reasons: string[]
  note: string
  reviewed_by_name: string
  reviewed_at: string | null
  created_at: string
}

export interface AnalyticsFilters {
  year: number
  month: number
  department?: Department
  employee?: number
  group?: number
  salary_type?: string
  status?: string
}

export interface DepartmentTotals {
  department: Department
  label: string
  accrued: string
  paid: string
  outstanding: string
  employees: number
}

export interface UpcomingPayment {
  payroll_id: number
  employee: number
  employee_name: string
  period_label: string
  planned_payment_date: string | null
  due: string
  status: PayrollStatus
  status_display: string
  is_overdue: boolean
}

/** Сводка директора: только утверждённые начисления, без предварительных оценок. */
export interface AnalyticsSummary {
  year: number
  month: number
  accrued: string
  paid: string
  outstanding: string
  awaiting_approval_amount: string
  employees: number
  cash_paid_in_month: string
  previous_month: { year: number; month: number; accrued: string; paid: string; outstanding: string; employees: number }
  accrued_change: string
  accrued_change_percent: string | null
  by_department: DepartmentTotals[]
  pending_approval_count: number
  review_required_count: number
  completed_cycles_without_accrual: number
  open_cycles: number
  upcoming_payments: UpcomingPayment[]
  history: { year: number; month: number; accrued: string; paid: string; outstanding: string; cash_paid: string }[]
}

export interface TeacherReportLine {
  line_id: number
  line_type: string
  line_type_display: string
  description: string
  group: number | null
  group_name: string
  course_name: string
  subject_name: string
  /** Уроков блока, проведённых сотрудником (доля); null — весь блок. */
  lessons_taught: number | null
  students: number | null
  price_per_student: string | null
  percentage: string | null
  lessons_done: number | null
  target_lessons: number | null
  completed_on: string | null
  rate: string | null
  accrued: string
}

export interface TeacherReportPayroll {
  payroll_id: number
  employee: number
  employee_name: string
  department: Department
  department_display: string
  period_label: string
  period_type: PeriodType
  salary_type: SalaryType
  salary_type_display: string
  status: PayrollStatus
  status_display: string
  planned_payment_date: string | null
  lines: TeacherReportLine[]
  accrued: string
  adjustments: string
  total: string
  paid: string
  due: string
}

export interface TeacherReport {
  year: number
  month: number
  range_label: string
  count: number
  next: string | null
  previous: string | null
  results: TeacherReportPayroll[]
  totals: { accrued: string; adjustments: string; total: string; paid: string; due: string }
  by_department: { department: Department; label: string; accrued: string; paid: string; due: string }[]
  by_group: { group_name: string; accrued: string }[]
  note: string
}

// ---------------------------------------------------------------------------
// План выплат
// ---------------------------------------------------------------------------

export type PayoutPlanStatus =
  | 'DRAFT' | 'SCHEDULED' | 'PARTIALLY_FUNDED' | 'READY' | 'PARTIALLY_PAID' | 'PAID' | 'CANCELLED'

export interface PayoutPlanTotals {
  planned: string
  paid: string
  /** Осталось выплатить по плану (с учётом выплат вне плана). */
  remaining: string
  prepared: string
  deficit: string
  readiness_percent: string
  employees: number
  status: PayoutPlanStatus
  status_display: string
}

export interface PayoutPlan {
  id: number
  title: string
  year: number
  month: number
  payout_date: string
  prepared_amount: string
  comment: string
  state: 'DRAFT' | 'APPROVED' | 'CANCELLED'
  cancel_reason: string
  version: number
  created_by_name: string
  created_at: string
  updated_at: string
  approved_by_name: string
  approved_at: string | null
  cancelled_by_name: string
  cancelled_at: string | null
  totals: PayoutPlanTotals
}

export interface PayoutPlanLine {
  id: number
  payroll: number
  employee: number
  employee_name: string
  position: string
  department: string
  department_display: string
  subjects: string[]
  salary_type: string
  salary_type_display: string
  period_label: string
  year: number
  month: number
  accrued: string
  /** Удержания расчёта — уже внутри остатка, план их повторно не вычитает. */
  deductions: string
  paid_before: string
  planned_amount: string
  paid_by_plan: string
  remaining_in_plan: string
  due_after_plan: string
  payroll_status: PayrollStatus
  payroll_status_display: string
  planned_payment_date: string | null
  basis: { description: string; amount: string }[]
  comment: string
  status: 'PLANNED' | 'PARTIALLY_PAID' | 'PAID' | 'SETTLED_OUTSIDE'
  status_display: string
}

export interface PayoutPlanDetail extends PayoutPlan {
  lines: PayoutPlanLine[]
  history: AuditEntry[]
}

export interface PayoutPlanFilters {
  year?: number
  month?: number
  payout_date?: string
  status?: string
  department?: string
  employee?: number
  page?: number
}

export interface PayoutPlanSummary {
  planned: string
  to_pay: string
  prepared: string
  deficit: string
  employees: number
  paid: string
  remaining_obligations: string
  plans: number
  readiness_percent: string
}

export interface PayoutCalendarDay {
  date: string
  to_pay: string
  prepared: string
  paid: string
  deficit: string
  employees: number
  readiness_percent: string
  plans: { id: number; title: string; status: PayoutPlanStatus; status_display: string }[]
}

export interface PayoutCalendar {
  days: PayoutCalendarDay[]
  suggestions: { date: string | null; amount: string; employees: number; payrolls: number; rule: string }[]
}

export interface PayoutCandidate {
  payroll: number
  employee: number
  employee_name: string
  department: string
  department_display: string
  period_label: string
  salary_type_display: string
  accrued: string
  paid: string
  due: string
  reserved: string
  available: string
  planned_payment_date: string | null
  status_display: string
}

export interface PayoutPlanCreateBody {
  title: string
  year: number
  month: number
  payout_date: string
  prepared_amount: string
  comment: string
  lines: { payroll: number; amount?: string | null }[]
}

export interface MyPlannedPayout {
  payout_date: string
  period_label: string
  payroll: number
  planned_amount: string
  paid: string
  remaining: string
}

// ---------------------------------------------------------------------------
// Налоги и удержания
// ---------------------------------------------------------------------------

export type DeductionKind = 'TAX' | 'CONTRIBUTION' | 'OTHER'
export type DeductionFrequency = 'MONTHLY' | 'PERIOD' | 'ONCE'
export type DeductionScope = 'EMPLOYEE' | 'DEPARTMENT' | 'ALL'

export interface DeductionRule {
  id: number
  series: string
  name: string
  kind: DeductionKind
  kind_display: string
  calc_type: 'FIXED'
  calc_type_display: string
  amount: string
  frequency: DeductionFrequency
  frequency_display: string
  scope: DeductionScope
  scope_display: string
  employee: number | null
  employee_name: string
  department: string
  department_display: string
  effective_from: string
  effective_to: string | null
  is_active: boolean
  description: string
  previous_version: number | null
  next_version: number | null
  usage: { locked_payrolls: number; draft_payrolls: number; used_until: string | null; can_correct: boolean }
  created_by_name: string
  created_at: string
  updated_at: string
}

export interface DeductionRuleBody {
  name: string
  kind: DeductionKind
  amount: string
  frequency: DeductionFrequency
  scope: DeductionScope
  employee: number | null
  department: string
  effective_from: string
  effective_to: string | null
  is_active: boolean
  description: string
}

export interface DeductionEffects {
  payrolls_recalculated: number[]
  payrolls_failed: { payroll_id: number; error: string }[]
}

export type MyDeductionStatus = 'WITHHELD' | 'PARTIAL' | 'NOT_WITHHELD' | 'PENDING'

/** Своё удержание за месяц (одна запись на правило и месяц). */
export interface MyDeduction {
  id: number
  name: string
  kind: DeductionKind
  kind_display: string
  year: number
  month: number
  period_label: string
  month_amount: string
  withheld: string
  remaining: string
  status: MyDeductionStatus
  status_display: string
  applied_at: string | null
}

// ---------------------------------------------------------------------------
// Заработок на текущий момент (единый расчёт для сотрудника и бухгалтера)
// ---------------------------------------------------------------------------

export type EarningsSource = 'OPEN_BLOCK' | 'ACCRUAL_PENDING' | 'PAYROLL_DRAFT' | 'PAYROLL_OFFICIAL' | 'REVIEW'

export interface EarningsAmounts {
  gross: string
  tax: string
  other_deductions: string
  net: string
}

export interface EarningsItem {
  source: EarningsSource
  source_display: string
  official: boolean
  year: number
  month: number
  period_label: string
  gross: string
  planned_payment_date: string | null
  payroll_id: number | null
  // блоки
  cycle_id?: number
  cycle_number?: number
  group_name?: string
  course_name?: string
  subject_name?: string
  lessons_taught?: number | null
  lessons_done?: number
  required_lessons?: number
  student_count?: number
  price_per_student?: string
  percentage?: string
  formula?: string
  // расчёты
  payroll_status_display?: string
  deductions?: string
  paid?: string
  due?: string | null
  lines?: { description: string; amount: string }[]
}

export interface EarningsDeduction {
  name: string
  kind: DeductionKind
  kind_display: string
  year: number
  month: number
  period_label: string
  month_amount: string
  amount: string
  remaining: string
}

export type PayoutScheduleStatus = 'SCHEDULED' | 'PARTIALLY_PAID' | 'PAID'

export interface PayoutScheduleItem {
  source: EarningsSource
  source_display: string
  official: boolean
  gross: string
  period_label: string
  payroll_id: number | null
  // расчёт зарплаты
  payroll_status_display?: string
  paid?: string
  due?: string | null
  blocks?: { description: string; subject_name: string; group_name: string; cycle_number: number | null; completed_on: string | null; amount: string }[]
  // завершённый / незавершённый блок вне расчёта
  subject_name?: string
  group_name?: string
  cycle_number?: number
  lessons_taught?: number | null
  required_lessons?: number
  completed_on?: string | null
}

export interface PayoutScheduleAmounts {
  gross: string
  tax: string
  other_deductions: string
  net: string
}

export interface PayoutScheduleEntry extends PayoutScheduleAmounts {
  date: string | null
  date_note: string
  paid: string
  remaining: string
  status: PayoutScheduleStatus
  status_display: string
  official_due: string
  not_yet_official: string
  fully_official: boolean
  items: PayoutScheduleItem[]
}

export interface NotIncludedEarnings extends PayoutScheduleAmounts {
  note: string
  items: PayoutScheduleItem[]
}

export interface PayoutCalendarByDate extends PayoutScheduleAmounts {
  date: string | null
  date_note: string
  paid: string
  remaining: string
  status: PayoutScheduleStatus
  status_display: string
  employees: (PayoutScheduleEntry & { employee: number; employee_name: string })[]
}

export interface PayoutScheduleResponse {
  as_of: string
  dates: PayoutCalendarByDate[]
  not_included: (NotIncludedEarnings & { employee: number; employee_name: string })[]
  not_included_total: PayoutScheduleAmounts
}

export interface Earnings {
  as_of: string
  /** Выплаты по плановым датам (15-е / 1-е); каждая сумма — в одной дате. */
  schedule: PayoutScheduleEntry[]
  /** Заработок по незавершённым блокам — ещё не включён ни в одну выплату. */
  not_included: NotIncludedEarnings
  earned: EarningsAmounts
  official: EarningsAmounts
  paid: string
  company_owes: string
  earned_unpaid: string
  next_payment_date: string | null
  difference: string
  difference_reasons: { source: EarningsSource; label: string; amount: string }[]
  items: EarningsItem[]
  deductions: EarningsDeduction[]
}

export interface EarningsRow {
  employee: number
  employee_name: string
  position: string
  salary_type: string
  salary_type_display: string
  department: string
  earned: EarningsAmounts
  official: EarningsAmounts
  paid: string
  company_owes: string
  earned_unpaid: string
  next_payment_date: string | null
  difference: string
  difference_reasons: { source: EarningsSource; label: string; amount: string }[]
}
