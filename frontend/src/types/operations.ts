/** Операционный модуль (backend: apps.operations). Все числа считает сервер;
 * `null` — «нет данных», никогда не подставленный 0. */

export type Department = 'management' | 'academy' | 'sales' | 'marketing' | 'hr' | 'finance'
export type OpsPeriod = 'today' | 'yesterday' | 'this_week' | 'this_month' | 'last_month' | 'custom'
export type TaskStatus = 'pending' | 'in_progress' | 'review' | 'completed' | 'rejected' | 'overdue' | 'cancelled'
export type Priority = 'low' | 'medium' | 'high' | 'critical'
export type TaskAction = 'start' | 'submit' | 'approve' | 'reject' | 'cancel' | 'reopen' | 'edit'

export interface Option<T extends string = string> {
  value: T
  label: string
}

export interface Person {
  id: number
  full_name: string
  role: string
  role_label: string
  department: Department
}

export interface OpsFiltersParams {
  period?: OpsPeriod
  start_date?: string
  end_date?: string
  department?: string
  role?: string
  employee?: string
}

export interface FiltersEcho {
  period: OpsPeriod
  label: string
  start: string
  end: string
}

// --- Задачи -----------------------------------------------------------------

export interface TaskListItem {
  id: number
  title: string
  department: Department
  department_label: string
  assignee: Person | null
  created_by: Person
  priority: Priority
  priority_label: string
  category: string
  category_label: string
  status: TaskStatus
  stored_status: TaskStatus
  status_label: string
  start_date: string | null
  deadline: string | null
  requires_approval: boolean
  occurrence_date: string | null
  is_recurring: boolean
  checklist_total: number
  checklist_done: number
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface ChecklistItem {
  id: number
  text: string
  position: number
  is_done: boolean
  done_by: Person | null
  done_at: string | null
}

export interface TaskComment {
  id: number
  author: Person
  text: string
  created_at: string
}

export interface TaskAttachment {
  id: number
  original_name: string
  content_type: string
  size: number
  uploaded_by: Person
  created_at: string
  download_url: string
}

export interface TaskHistoryItem {
  id: number
  actor: Person | null
  action: string
  action_label: string
  from_status: string
  to_status: string
  changes: Record<string, unknown>
  comment: string
  created_at: string
}

export interface TaskReview {
  id: number
  reviewer: Person
  decision: 'approved' | 'rejected'
  comment: string
  created_at: string
}

export interface TaskDetail extends TaskListItem {
  description: string
  reviewer: Person | null
  checklist: ChecklistItem[]
  comments: TaskComment[]
  attachments: TaskAttachment[]
  history: TaskHistoryItem[]
  reviews: TaskReview[]
  actions: TaskAction[]
  started_at: string | null
  submitted_at: string | null
  cancelled_at: string | null
}

export interface TaskInput {
  title: string
  description?: string
  department?: Department
  assignee?: number | null
  reviewer?: number | null
  priority?: Priority
  category?: string
  start_date?: string | null
  deadline?: string | null
  requires_approval?: boolean
  checklist?: string[]
}

export interface TasksParams {
  status?: string
  department?: string
  priority?: string
  category?: string
  assignee?: string
  role?: string
  mine?: '1'
  created?: '1'
  to_review?: '1'
  recurring?: '1'
  recurrence?: string
  search?: string
  deadline_from?: string
  deadline_to?: string
  page?: number
  page_size?: number
}

export interface TasksMeta {
  statuses: Option<TaskStatus>[]
  priorities: Option<Priority>[]
  categories: Option[]
  departments: Option<Department>[]
  recurrence: Option[]
  assignees: Person[]
  can_assign_others: boolean
  can_oversee: boolean
  me: Person
}

export type MyTaskSection = 'overdue' | 'today' | 'upcoming' | 'in_progress' | 'review' | 'completed' | 'to_review'

export type MyTasks = Record<MyTaskSection, TaskListItem[]> & { counts: Record<string, number> }

export interface Recurrence {
  id: number
  title: string
  description: string
  department: Department
  assignee: number
  assignee_info: Person
  priority: Priority
  category: string
  requires_approval: boolean
  checklist: string[]
  frequency: 'daily' | 'weekly' | 'monthly'
  frequency_label: string
  weekdays: number[]
  month_day: number | null
  due_time: string | null
  starts_on: string
  ends_on: string | null
  is_active: boolean
  last_generated_on: string | null
  occurrences_count: number
}

export type RecurrenceInput = Partial<Omit<Recurrence, 'id' | 'assignee_info' | 'frequency_label' | 'occurrences_count'>>

// --- Отчёты сотрудников ------------------------------------------------------

export type ReportKind = 'daily' | 'weekly' | 'monthly'
export type ReportStatus = 'draft' | 'submitted' | 'accepted' | 'returned'

export interface WorkReport {
  id: number
  author: Person
  department: Department
  department_label: string
  kind: ReportKind
  kind_label: string
  period_start: string
  period_end: string
  done: string
  plans: string
  problems: string
  metrics: Record<string, number | boolean>
  status: ReportStatus
  status_label: string
  submitted_at: string | null
  reviewed_by: Person | null
  reviewed_at: string | null
  review_comment: string
  created_at: string
}

export interface MetricField {
  key: string
  label: string
  type: 'int' | 'money' | 'bool'
}

export interface Obligation {
  kind: ReportKind
  period_start: string
  period_end: string
  due: string
  status: 'submitted' | 'missing' | 'pending'
  report_id: number | null
}

export interface WorkReportsMeta {
  kinds: Option<ReportKind>[]
  statuses: Option<ReportStatus>[]
  metrics: MetricField[]
  obligations: Obligation[]
  today: string
}

export interface Notification {
  id: number
  kind: string
  kind_label: string
  title: string
  message: string
  link: string
  is_read: boolean
  read_at: string | null
  created_at: string
}

// --- Кабинет ------------------------------------------------------------------

export interface OpsMeta {
  periods: Option<OpsPeriod>[]
  departments: Option<Department>[]
  roles: (Option & { department: Department })[]
  employees: Person[]
  subjects: { id: number; name: string }[]
  groups: { id: number; name: string }[]
  metrics: MetricInfo[]
  kpi_periods: Option[]
  issue_kinds: Option[]
  issue_statuses: Option[]
  priorities: Option<Priority>[]
  report_kinds: Option[]
  employee_report_kinds: Option<ReportKind>[]
  can_view_finance: boolean
  today: string
}

export interface MetricInfo {
  key: string
  label: string
  unit: 'percent' | 'count' | 'money' | 'minutes'
  departments: Department[]
  higher_is_better: boolean
  department_level: boolean
  employee_level: boolean
  financial: boolean
  source: string
  roles: string[]
}

export interface TaskCounts {
  open: number
  overdue: number
  review: number
  completed: number
}

export interface SubmissionSummary {
  expected: number
  submitted: number
  missing: number
  pending: number
  rate: number | null
}

export interface AttendanceSummary {
  counts: Record<string, number>
  expected_days: number
  attended_days: number
  attendance_rate: number | null
  punctuality_rate: number | null
  worked_hours: number
  late_minutes: number
}

export interface DepartmentRow {
  key: Department
  label: string
  employees: number
  tasks: TaskCounts & { completion_rate: number | null }
  attendance_rate: number | null
  reports: SubmissionSummary
  open_issues: number
  performance: number | null
}

export interface ShortTask {
  id: number
  title: string
  department: Department
  department_label: string
  assignee: { id: number; full_name: string; role_label: string } | null
  priority: Priority
  priority_label: string
  status: TaskStatus
  deadline: string | null
}

export interface IssueBrief {
  id: number
  title: string
  priority: Priority
  kind: string
  kind_label: string
  department_label: string
  responsible: { id: number; full_name: string; role_label: string } | null
  detected_at: string
}

export interface ActivityEvent {
  at: string
  type: 'task' | 'report' | 'issue'
  action: string
  title: string
  actor: { id: number; full_name: string; role_label: string } | null
  link: string
}

export interface Dashboard {
  filters: FiltersEcho
  metrics: {
    total_employees: number
    active_employees: number
    tasks_completed: number
    tasks_in_progress: number
    tasks_overdue: number
    pending_reviews: number
    attendance_rate: number | null
    reports_submitted: number
    reports_expected: number
    kpi: { targets: number; measured: number; below_target: number; achievement: number | null }
    overall_performance: number | null
  }
  previous: { tasks_completed: number; attendance_rate: number | null; label: string }
  departments: DepartmentRow[]
  today_tasks: ShortTask[]
  overdue_tasks: ShortTask[]
  overdue_total: number
  attendance: AttendanceSummary & { today: AttendanceSummary | null }
  reports: SubmissionSummary
  attention: { total: number; critical: number; by_kind: Record<string, number>; top: IssueBrief[] }
  students: StudentsOverview | null
  activity: ActivityEvent[]
}

export interface StudentsOverview {
  active_students: number
  active_groups: number
  problem_students: number
  risk: number
  frequent_absence: number
}

export interface EmployeeCard {
  id: number
  full_name: string
  role: string
  role_label: string
  department: Department
  department_label: string
  position: string
  photo: string | null
  teacher_id: number | null
  is_active: boolean
  joined: string
  last_login: string | null
}

export interface EmployeeRow extends EmployeeCard {
  tasks: TaskCounts
  reports: SubmissionSummary
  attendance: AttendanceSummary | null
}

export interface KpiValue extends MetricInfo {
  actual: number | null
  target: number | null
  achievement: number | null
  previous?: number | null
  trend?: { direction: 'up' | 'down' | 'stable'; change: number | null } | null
}

export interface EmployeeProfile {
  employee: EmployeeCard
  tasks: TaskCounts & { completed_in_period: number; overdue_items: TaskListItem[]; open_items: TaskListItem[] }
  reports: {
    summary: SubmissionSummary
    obligations: { kind: ReportKind; period_start: string; status: string; due: string; report_id: number | null }[]
    recent: { id: number; kind: ReportKind; kind_label: string; period_start: string; status: ReportStatus; status_label: string }[]
  }
  attendance: { summary: AttendanceSummary; days: AttendanceRow[] } | null
  kpi: KpiValue[]
  history: { month: string; tasks_completed: number; task_completion_rate: number | null }[]
  issues: { id: number; title: string; kind: string; priority: Priority; status: string }[]
  subordinates: EmployeeCard[]
}

export interface JournalControl {
  status: string
  status_label: string
  lessons_due: number
  lessons_closed: number
  not_closed: number
  upcoming: number
  attendance_missing: number
  homework_awaiting_review: number
  homework_missing: number
  homework_checked: number
  grades_missing: number
  last_activity_at: string | null
  completion: number | null
  issues: string[]
}

export interface TrainerRow {
  id: number
  user_id: number
  name: string
  photo: string | null
  position: string
  subjects: string[]
  groups: { id: number; name: string; kpi: number | null }[]
  students: number
  is_active: boolean
  kpi: number | null
  kpi_level: string
  kpi_target: number | null
  kpi_achievement: number | null
  attendance_rate: number | null
  homework_rate: number | null
  journal: JournalControl
  reports: SubmissionSummary
  tasks: TaskCounts
  warnings: { key: string; label: string }[]
}

export interface TrainersResponse {
  filters: FiltersEcho
  summary: { trainers: number; with_warnings: number; average_kpi: number | null; warnings: Record<string, number> }
  trainers: TrainerRow[]
  warning_labels: Record<string, string>
}

export interface ControlRow {
  key: string
  teacher: { id: number; name: string } | null
  group: { id: number; name: string }
  subjects: { id: number; name: string }[]
  lessons: { completed: number; total: number; percent: number | null; not_closed: number; upcoming: number }
  attendance: { completed: number; total: number; percent: number | null }
  homework: { completed: number; total: number; percent: number | null; awaiting_review: number; missing: number }
  grades: { completed: number; total: number; percent: number | null; students_missing: number }
  status: string
  status_label: string
  issues: string[]
  last_activity_at: string | null
}

export interface ProblemStudent {
  student_id: number
  name: string
  group: { id: number; name: string } | null
  attendance: number | null
  absent: number
  consecutive_absences: number
  homework: number | null
  homework_missed: number
  last_teacher: string
  last_activity: string | null
  status: string
  status_label: string
  categories: string[]
  category_labels: string[]
}

export interface TrainerDetail {
  trainer: TrainerRow
  control: { summary: Record<string, number | null | Record<string, number>>; rows: ControlRow[] }
  kpi: Record<string, unknown> & { kpi?: number | null }
  problem_students: ProblemStudent[]
  reports: Obligation[]
  monthly_reports: { id: number; year: number; month: number; comment: string; updated_at: string }[]
}

export interface TeamLeadRow {
  id: number
  name: string
  team_size: number
  worklog_entries: number
  reports: Record<string, number>
  report_obligations: SubmissionSummary
  reports_reviewed: number
  tasks: TaskCounts
  academy_control: { attention: number; problem_lessons: number; attendance_completion: number | null; homework_completion: number | null }
}

export interface AssistantRow {
  id: number
  name: string
  parents_contacted: number | null
  absences_followed_up: number | null
  tables_updated: number | null
  report_obligations: SubmissionSummary
  tasks: TaskCounts
}

export interface SalesFunnel {
  leads_new?: number
  leads_processed?: number
  calls?: number
  meetings?: number
  trials_scheduled?: number
  trials_attended?: number
  sales?: number
  revenue?: number
  conversion?: number | null
  trial_attendance?: number | null
  reports?: number
}

export interface SalesManagerRow extends EmployeeCard {
  funnel: SalesFunnel
  sales_plan: number | null
  sales_fact: number | null
  plan_achievement: number | null
  tasks: TaskCounts
  reports: SubmissionSummary
}

export interface SalesResponse {
  source: string
  crm_connected: boolean
  department: SalesFunnel & { sales_plan: number | null; plan_achievement: number | null }
  managers: SalesManagerRow[]
  daily: { date: string; leads_processed?: number; sales?: number; calls?: number }[]
}

export interface HeadOfSalesRow extends EmployeeCard {
  own_reports: number
  planning_meetings: number
  one_to_ones: number | null
  issues_resolved: number | null
  crm_checks: number | null
  team_reports_reviewed: number
  team_reports_waiting: number
  team_tasks_created: number
  team_tasks_completed: number
  tasks: TaskCounts
  reports: SubmissionSummary
}

export interface HeadOfSalesResponse {
  heads: HeadOfSalesRow[]
  department: SalesResponse['department']
  managers: SalesManagerRow[]
  team_report_rate: number | null
  crm_connected: boolean
}

export interface CampaignRow {
  id: number
  name: string
  channel: string
  status: string
  status_label: string
  start_date: string
  end_date: string | null
  responsible: string | null
  leads: number
  sales: number
  conversion: number | null
  result: string
  budget?: string
  spent?: string
  cost_per_lead?: string | null
}

export interface MarketingResponse {
  summary: {
    content_planned: number
    content_published: number
    plan_completion: number | null
    campaigns: number
    campaigns_active: number
    leads: number
    campaign_sales: number
    conversion: number | null
    tasks_open: number
    tasks_overdue: number
    tasks_done: number
    budget?: string
    spent?: string
    cost_per_lead?: number | null
  }
  campaigns: CampaignRow[]
  calendar: { id: number; title: string; date: string; channel: string; status: string; status_label: string; responsible: string | null }[]
  budget_visible: boolean
  team: (EmployeeCard & { tasks: TaskCounts; content_published: number })[]
}

export interface HrResponse {
  active_employees: number
  inactive_employees: number
  new_employees: EmployeeCard[]
  new_employees_count: number
  by_department: { key: Department; label: string; count: number }[]
  vacancies: { open: number; draft: number; paused: number }
  recruitment: { applications: number; funnel: { status: string; label: string; count: number }[]; interviews: number; hired: number }
  team: (EmployeeCard & { tasks: TaskCounts })[]
  onboarding_tracked: boolean
  documents_tracked: boolean
}

export interface AttendanceRow {
  user: { id: number; full_name: string; role: string; role_label: string; department: Department }
  date: string
  status: string
  status_label: string
  check_in: string | null
  check_out: string | null
  worked_minutes: number
  late_minutes: number
  expected_start: string | null
  expected_end: string | null
  location: string | null
  geo_verified: boolean
  distance_m: number | null
  adjusted: boolean
}

export interface StaffAttendanceResponse {
  filters: FiltersEcho
  summary: AttendanceSummary
  rows: AttendanceRow[]
  departments: (AttendanceSummary & { key: Department; label: string })[]
  employees: (AttendanceSummary & { user: AttendanceRow['user'] })[]
  statuses: Option[]
  leave_tracking: boolean
}

export interface DailyControl {
  date: string
  tasks: { completed: ShortTask[]; overdue: ShortTask[]; completed_count: number; overdue_count: number }
  reports: SubmissionSummary & { missing: { user: { id: number; full_name: string; role_label: string }; kind: ReportKind; due: string }[] }
  journals: { summary: Record<string, number | null | Record<string, number>>; problems: ControlRow[] }
  attendance: AttendanceSummary & { absent: AttendanceRow[]; late: AttendanceRow[] }
  kpi: Dashboard['metrics']['kpi']
  students: ProblemStudent[]
  issues: { open: number; new_today: number; items: (Omit<IssueBrief, 'kind' | 'detected_at'>)[] }
  departments: { key: Department; label: string; completed: number; overdue: number; reports_missing: number; absent: number; late: number }[]
}

export interface KpiOverview {
  filters: FiltersEcho
  period_type: string
  previous: FiltersEcho
  departments: { department: Department; label: string; metrics: KpiValue[] }[]
  employee: { id: number; full_name: string } | null
}

export interface KpiTarget {
  id: number
  metric: string
  metric_label: string
  department: Department
  department_label: string
  employee: number | null
  employee_info: Person | null
  period: 'daily' | 'weekly' | 'monthly'
  period_label: string
  target_value: string
  valid_from: string
  valid_to: string | null
  note: string
}

export type KpiTargetInput = Partial<Pick<KpiTarget, 'metric' | 'department' | 'employee' | 'period' | 'target_value' | 'valid_from' | 'valid_to' | 'note'>>

export interface ReportsResponse {
  filters: FiltersEcho
  kind: string
  kinds: Option[]
  sheets: { title: string; headers: string[]; rows: (string | number)[][]; total: number }[]
  employee_reports: { id: number; author: Person; kind: ReportKind; kind_label: string; period_start: string; status: ReportStatus; status_label: string; submitted_at: string | null }[]
  history: { id: number; kind: string; format: string; filters: Record<string, string | null>; rows: number; created_by: Person | null; created_at: string }[]
}

export interface Issue {
  id: number
  kind: string
  kind_label: string
  title: string
  description: string
  priority: Priority
  priority_label: string
  status: 'open' | 'in_progress' | 'resolved' | 'dismissed'
  status_label: string
  department: Department
  department_label: string
  responsible: Person | null
  object_type: string
  object_id: number | null
  link: string
  detected_at: string
  last_seen_at: string
  times_detected: number
  reopen_count: number
  auto_detected: boolean
  resolved_at: string | null
}

export interface IssueDetail extends Issue {
  events: { id: number; actor: Person | null; action: string; action_label: string; from_status: string; to_status: string; comment: string; created_at: string }[]
  resolved_by: Person | null
  payload: Record<string, unknown>
}

export interface IssuesParams {
  status?: string
  kind?: string
  department?: string
  priority?: string
  responsible?: string
  repeated?: '1'
  q?: string
  page?: number
}

export interface OpsSettings {
  required_reports: Record<string, ReportKind[]>
  daily_report_due: string
  deadline_reminder_hours: number
  problem_group_attendance: number
  detect_staff_absence: boolean
  notify_telegram: boolean
  operations_director_sees_marketing_budget: boolean
  updated_at: string
  roles?: Option[]
  report_kinds?: Option<ReportKind>[]
}

export interface DepartmentDetail {
  department: DepartmentRow
  employees: EmployeeRow[]
  kpi: KpiOverview['departments'][number]
  roles: Option[]
}
