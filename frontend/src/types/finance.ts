/** Финансы студентов — договоры по программам, учебные месяцы, платежи, чеки
 * (/api/v1/accounting/billing/). Суммы — строки Decimal, без float. */

export type InvoiceStatus = 'DRAFT' | 'OPEN' | 'PARTIALLY_PAID' | 'PAID' | 'OVERDUE' | 'VOID'
export type InvoiceKind = 'PACKAGE' | 'MONTH' | 'COURSE'
/** awaiting — ожидается оплата; deadline — последний срок; overdue — просрочка. */
export type PaymentStage = 'awaiting' | 'deadline' | 'overdue' | 'paid' | 'draft' | 'void'
export type ContractStatus = 'ACTIVE' | 'PAUSED' | 'INACTIVE' | 'COMPLETED'
export type PaymentMode = 'MONTHLY' | 'FULL_PREPAY'
export type ReservationMode = 'FIRST_MONTH' | 'COURSE_TOTAL'
export type QueueKind = 'to_pay' | 'soon' | 'overdue' | 'all'
export type PaymentTarget = 'auto' | 'invoice' | 'advance'

export interface FinanceMe {
  role: 'accountant' | 'director' | 'manager' | null
  read_only: boolean
  can_view: boolean
  can_view_money: boolean
  is_manager: boolean
  is_accountant: boolean
  is_director: boolean
  can_record_payments: boolean
  can_register: boolean
  can_manage_plans: boolean
  can_manage_settings: boolean
  can_view_audit: boolean
  max_manager_discount_percent: string
}

export interface Option {
  value: string
  label: string
}

export interface FinanceOptions {
  plans: { id: number; name: string; subject: number | null; course: number | null; duration_months: number | null
    allow_monthly: boolean; allow_full_prepay: boolean }[]
  programs: { id: number; name: string }[]
  subjects: { id: number; name: string }[]
  groups: { id: number; name: string }[]
  accountants: { id: number; name: string }[]
  invoice_statuses: Option[]
  payment_methods: Option[]
  payment_modes: Option[]
  reservation_modes: Option[]
  contract_statuses: Option[]
  contact_channels: Option[]
  contact_results: Option[]
}

export interface FocusInvoice {
  id: number
  number: string
  kind: InvoiceKind
  month_number: number
  amount: string
  paid: string
  balance: string
  due_lesson: number | null
  due_date: string | null
  status: InvoiceStatus
  status_display: string
}

export interface NextMonth {
  month_number: number
  cost: string
  covered: string
  to_pay: string
}

export interface QueueRow {
  profile: number
  student: number
  student_name: string
  group: number | null
  group_name: string | null
  program: string | null
  plan: number
  plan_name: string
  subject_name: string | null
  parent_name: string
  parent_phone: string
  contract_status: ContractStatus
  contract_status_display: string
  is_course: boolean
  payment_mode: PaymentMode
  payment_mode_display: string
  duration_months: number | null
  month_number: number | null
  lessons_used: number
  lessons_total: number
  final_course_price: string | null
  discount_amount: string | null
  stage: PaymentStage
  focus_invoice: FocusInvoice | null
  due_now: string
  overdue_amount: string
  overdue_lessons: number
  overdue_days: number
  credit: string
  last_contact_at: string | null
  last_contact_result: string | null
  next_month?: NextMonth | null
}

export interface QueuePage {
  count: number
  page: number
  page_size: number
  results: QueueRow[]
}

export interface QueueFilters {
  search?: string
  group?: number
  program?: number
  plan?: number
  ordering?: string
  contract_status?: ContractStatus
  page?: number
  page_size?: number
}

export interface QueueCounts {
  to_pay: number
  soon: number
  overdue: number
}

export interface Invoice {
  id: number
  number: string
  profile: number
  student_name: string
  package_number: number
  month_number: number | null
  lessons_used: number
  lessons_total: number
  kind: InvoiceKind
  kind_display: string
  amount: string
  amount_paid: string
  amount_adjusted: string
  balance: string
  status: InvoiceStatus
  status_display: string
  stage: PaymentStage
  issue_date: string
  /** Учебный / финансовый период начисления (не дата записи и не дата выставления). */
  period_date: string
  due_date: string
  due_lesson: number | null
  due_reached_on: string | null
  overdue_since: string | null
  paid_at: string | null
}

export interface StudyMonth {
  id: number
  number: number
  month_number: number | null
  status: 'PLANNED' | 'ACTIVE' | 'COMPLETED' | 'CANCELLED'
  lessons_total: number
  lessons_used: number
  lessons_remaining: number
  final_price: string
  started_on: string | null
  completed_on: string | null
  invoice: { id: number; number: string; status: InvoiceStatus; balance: string; amount: string; kind: InvoiceKind } | null
}

export interface Allocation {
  id: number
  invoice: number
  invoice_number: string
  /** Период начисления, которое оплачено этой частью платежа. */
  invoice_period_date: string
  amount: string
  status: 'ACTIVE' | 'REVERSED'
}

export interface Payment {
  id: number
  billing_profile: number
  student: number
  student_name: string
  group_name: string
  program_name: string
  kind: 'payment' | 'refund'
  purpose: string
  purpose_display: string
  amount: string
  received_date: string
  method: string
  method_display: string
  reference: string
  comment: string
  status: 'confirmed' | 'void'
  void_reason: string
  unallocated: string | null
  allocations: Allocation[]
  receipt: { id: number; number: string; status: 'ISSUED' | 'CANCELLED' } | null
  created_by_name: string | null
  created_at: string
}

export interface Contract {
  id: number
  student: number
  student_name: string
  group: number | null
  group_name: string | null
  plan: number
  plan_name: string
  program_name: string | null
  subject_name: string | null
  status: ContractStatus
  status_display: string
  start_date: string
  parent_name: string
  parent_phone: string
  payment_mode: PaymentMode
  payment_mode_display: string
  reservation_allocation: ReservationMode
  reservation_allocation_display: string
  duration_months: number | null
  lessons_per_month: number | null
  deadline_lessons: number | null
  month_price: string | null
  standard_course_price: string | null
  final_course_price: string | null
  discount_enabled: boolean
  discount_amount: string
  discount_reason: string
  is_course: boolean
  pending_terms: { id: number; final_course_price: string | null; discount_amount: string; reason: string } | null
  special_terms: string
}

export interface MoneySummary {
  received: string
  refunded: string
  net_received: string
  reservation_received: string
  reservation_unused: string
  allocated: string
  adjusted: string
  credit: string
  due_now: string
  overdue: string
  paid_total: string
  standard_course_price: string | null
  final_course_price: string | null
  discount_amount: string
  outstanding: string
  future: string | null
}

export interface Reservation {
  id: number
  expected_amount: string
  status: 'PENDING' | 'PAID' | 'CANCELLED'
  paid_amount: string | null
  reserved_until: string | null
}

export interface Contact {
  id: number
  staff_name: string
  contacted_at: string
  channel_display: string
  result_display: string
  comment: string
  promised_payment_date: string | null
  next_contact_date: string | null
}

export interface ContractCard {
  contract: Contract
  row: QueueRow
  summary: MoneySummary
  months: StudyMonth[]
  invoices: Invoice[]
  reservations: Reservation[]
  payments?: Payment[]
  contacts?: Contact[]
  credit?: string
}

export interface PaymentPreview {
  amount: string
  obligation: string
  paid_before: string
  obligation_balance_after: string
  to_credit: string
  due_now_before: string
  due_now_after: string
  credit_before: string
  credit_after: string
  outstanding_before: string
  outstanding_after: string
  allocations: { invoice: number; number: string; month_number: number | null; payment: string; balance_after: string }[]
}

export interface PaymentBody {
  profile: number
  amount: string
  /** Дата фактического поступления денег (можно прошлую). */
  received_date: string
  method: string
  purpose?: 'tuition' | 'prepayment'
  mode: PaymentTarget
  invoice?: number | null
  reference?: string
  comment?: string
  payer_name?: string
}

export interface Receipt {
  id: number
  number: string
  payment: number
  profile: number
  student_name: string
  kind: 'PAYMENT' | 'REFUND'
  kind_display: string
  status: 'ISSUED' | 'CANCELLED'
  status_display: string
  amount: string
  received_date: string
  payer_name: string
  issued_at: string
  issued_by_name: string | null
  print_count: number
  cancel_reason: string
  rows: { label: string; value: string }[]
  academy: { name: string; details: string; footer: string }
}

export interface ContractBody {
  student: number
  plan: number
  start_date?: string | null
  parent_name?: string
  parent_phone?: string
  payment_mode: PaymentMode
  reservation_allocation: ReservationMode
  discount_enabled: boolean
  final_course_price?: string | null
  discount_reason?: string
  reservation_amount?: string | null
  reservation_received?: boolean
  initial_payment?: string | null
  payment_method?: string
  payer_name?: string
  special_terms?: string
}

export interface LmsStudent {
  id: number
  name: string
  group: number | null
  group_name: string | null
  status: string
  status_display: string
  parent_phone: string
  profiles: { id: number; status: ContractStatus; plan_name: string; payment_state: string; debt: string }[]
}

export interface Plan {
  id: number
  name: string
  subject: number | null
  subject_name: string | null
  course: number | null
  course_name: string | null
  duration_months: number | null
  payment_deadline_lessons: number
  allow_monthly: boolean
  allow_full_prepay: boolean
  absence_policy: string
  is_active: boolean
  current: { lessons_per_package: number; package_price: string; effective_from: string; standard_course_price: string | null } | null
}

export interface PlanBody {
  name: string
  course: number | null
  subject: number | null
  duration_months: number | null
  lessons_per_package: number
  package_price: string
  payment_deadline_lessons: number
  allow_monthly: boolean
  allow_full_prepay: boolean
  effective_from: string
}

export interface Analytics {
  date_from: string
  date_to: string
  received: {
    basis: string
    gross: string
    count: number
    refunds: string
    refunds_count: number
    net: string
    reversed: string
    reversed_count: number
    by_method: { method: string; method_display: string; amount: string; count: number }[]
  }
  expected: {
    basis: string
    amount: string
    count: number
    students: number
    paid: string
    unpaid: string
    paid_count: number
    partial_count: number
    overdue_count: number
  }
  difference: string
  debt_end: string
  discounts: { amount: string; contracts: number }
  reservations: string
  prepayment: string
  by_program: { program: number | null; program_name: string; received: string; refunded: string; net: string
    expected: string; expected_paid: string; expected_unpaid: string; students: number }[]
}

export interface AuditRow {
  id: number
  created_at: string
  actor: string
  action: string
  action_display: string
  entity_type: string
  entity_id: number
  old_values: Record<string, unknown>
  new_values: Record<string, unknown>
  reason: string
}

export interface FinanceSettings {
  manager_max_discount_percent: string
  due_soon_lessons: number
  default_deadline_lessons: number
  accountant_refund_limit: string | null
  academy_name: string
  academy_details: string
  receipt_footer: string
  updated_at?: string
}

export interface FinanceDashboard {
  total_debt: string
  overdue_amount: string
  overdue_students: number
  students_awaiting: number
  active_students: number
  credit_total: string
  received: { amount: string; count: number; refunds: string; net: string }
}

/** Посещения студента и какие из них засчитаны в учебные месяцы (с причиной). */
export interface LessonBreakdown {
  attended: number
  marked: number
  counted: number
  priority_subject: string | null
  totals: Record<string, number>
  lessons: { lesson: number; date: string; group: string; subject: string | null; lesson_status: string
    attendance: string | null; reason: string; reason_display: string; month_number: number | null }[]
}

/** Выбранный финансовый период: месяц или произвольный диапазон дат. */
export type FinancePeriod =
  | { kind: 'month'; month: string }
  | { kind: 'range'; date_from: string; date_to: string }

export interface PeriodMonth {
  value: string
  label: string
  date_from: string
  date_to: string
  is_current: boolean
}

export interface PeriodsResponse {
  today: string
  current: string
  months: PeriodMonth[]
}

interface MonthAmount { month: string; label: string; amount: string; count: number }

/** Отчёт за период: поступления — по дате денег, начисления — по периоду начисления. */
export interface PeriodReport {
  date_from: string
  date_to: string
  label: string
  basis: { received: string; accrued: string; debt: string }
  received: {
    gross: string; count: number; refunds: string; refunds_count: number; net: string
    for_current_period: string; for_previous_periods: string; for_future_periods: string; to_credit: string
    previous_by_period: MonthAmount[]
    backdated: { amount: string; count: number }
  }
  accrued: {
    amount: string; count: number; students: number
    paid_in_advance: string; paid_in_period: string; adjusted_by_end: string; unpaid_at_end: string
    paid_later: string; paid_later_by_month: MonthAmount[]; adjusted_later: string; unpaid_now: string
  }
  debt: { opening: string; closing: string }
  debtors_at_end: { profile: number; student_name: string; group: string | null; subject: string | null
    parent_phone: string; debt: string; unpaid_now: string; oldest_period: string }[]
}
