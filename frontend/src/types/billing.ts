/** Оплата обучения по пакетам уроков (/api/v1/accounting/billing/). Суммы — строки Decimal. */

export type InvoiceStatus = 'DRAFT' | 'OPEN' | 'PARTIALLY_PAID' | 'PAID' | 'OVERDUE' | 'VOID'

export interface BillingCapabilities {
  can_view: boolean
  can_view_money: boolean
  is_manager: boolean
  is_accountant: boolean
  is_billing_admin: boolean
  can_record_payments: boolean
  can_manage_plans: boolean
  max_manager_discount_percent: string
}

export interface BillingFilters {
  group?: number
  subject?: number
  student?: number
  accountant?: number
  status?: InvoiceStatus
  date_from?: string
  date_to?: string
}

export interface InvoiceRow {
  invoice: number
  number: string
  profile: number
  student: number
  student_name: string
  group: string | null
  subject: string | null
  package_number: number
  amount: string
  paid: string
  balance: string
  due_date: string
  status: InvoiceStatus
  status_display: string
  parent_phone: string
  accountant: number | null
}

export interface ContactRow {
  id: number
  student: number
  student_name: string
  invoice: string | null
  staff: string
  contacted_at: string
  channel: string
  channel_display: string
  result: string
  result_display: string
  comment: string
  promised_payment_date: string | null
  next_contact_date: string | null
}

export interface BillingDashboard {
  date: string
  date_from: string
  date_to: string
  active_students: number
  students_awaiting: number
  invoices_awaiting: number
  total_debt: string
  overdue_invoices: number
  overdue_students: number
  overdue_amount: string
  due_soon_days: number
  due_soon: InvoiceRow[]
  received: { amount: string; count: number; refunds: string; refunds_count: number; net: string }
  credit_total: string
  credit_profiles: number
  partial: InvoiceRow[]
  packages_ending: number
  open_tasks: number
  follow_ups_due: number
  contacts: ContactRow[]
}

export interface DebtorRow {
  profile: number
  student: number
  student_name: string
  group: string | null
  subject: string | null
  parent_name: string
  parent_phone: string
  accountant: number | null
  accountant_name: string | null
  invoices: number
  debt: string
  overdue_amount: string
  oldest_due: string
  max_days_overdue: number
  has_partial: boolean
  credit: string
  task: number | null
  task_status: string | null
  promised_date: string | null
  next_contact_date: string | null
  last_contact_at: string | null
  last_contact_result: string | null
}

export interface Invoice {
  id: number
  number: string
  profile: number
  student: number
  student_name: string
  group_name: string | null
  subject_name: string | null
  package: number
  package_number: number
  amount: string
  amount_paid: string
  amount_adjusted: string
  balance: string
  status: InvoiceStatus
  status_display: string
  issue_date: string
  due_date: string
  paid_at: string | null
}

export interface BillingPayment {
  id: number
  billing_profile: number
  student: number
  student_name: string
  kind: 'payment' | 'refund'
  purpose: 'tuition' | 'reservation' | ''
  amount: string
  received_date: string
  method: string
  reference: string
  comment: string
  status: 'confirmed' | 'void'
  void_reason: string
  refund_of: number | null
  unallocated: string | null
  allocations: { id: number; invoice: number; invoice_number: string; amount: string; status: string }[]
  created_by_name: string | null
}

export interface TermsChange {
  id: number
  profile: number
  student_name: string
  custom_price: string | null
  discount_type: 'NONE' | 'PERCENT' | 'FIXED'
  discount_value: string
  reason: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  requested_by_name: string | null
  requested_at: string
  decided_by_name: string | null
  decided_at: string | null
  decision_comment: string
}

export interface BillingOptions {
  plans: { id: number; name: string; subject: number | null }[]
  subjects: { id: number; name: string }[]
  groups: { id: number; name: string }[]
  accountants: { id: number; name: string }[]
  invoice_statuses: { value: InvoiceStatus; label: string }[]
  contact_channels: { value: string; label: string }[]
  contact_results: { value: string; label: string }[]
}

export interface ContactBody {
  profile: number
  invoice?: number | null
  channel: string
  result: string
  comment?: string
  promised_payment_date?: string | null
  next_contact_date?: string | null
}

export interface PaymentBody {
  profile: number
  amount: string
  received_date: string
  method: string
  reference?: string
  comment?: string
  prepay_packages?: number
}
