import type { UserRole } from '@/types/auth'

/** `apps.users.hr.HREmployeeSerializer` — пароль никогда не возвращается. */
export interface HREmployee {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  role: UserRole
  role_label: string
  is_active: boolean
  /** false — коллега-HR: карточку видно, но менять нельзя. */
  can_manage: boolean
  created_at: string
  last_login: string | null
}

export interface HRRoleOption {
  value: UserRole
  label: string
}

/** `GET /api/v1/hr/employees/meta/` */
export interface HRMeta {
  roles: HRRoleOption[]
  protected_roles: HRRoleOption[]
}

export interface HREmployeeInput {
  username: string
  email: string
  first_name: string
  last_name: string
  role: UserRole
}

export interface HREmployeeCreateInput extends HREmployeeInput {
  password: string
  password_confirm: string
}

export interface HREmployeesParams {
  search?: string
  role?: string
  is_active?: 'true' | 'false'
  ordering?: string
  page?: number
}

export interface HRPerson {
  id: number
  full_name: string
  role_label: string
}

/** `apps.recruitment.services.reports.activity_brief` — запись журнала. */
export interface HRActivity {
  id: number
  kind: string
  kind_label: string
  message: string
  created_at: string
  actor: string | null
  candidate: { id: number; full_name: string } | null
  application: number | null
  employee: { id: number; full_name: string } | null
  from_status: string
  to_status: string
}

/** `GET /api/v1/hr/employees/:id/` — карточка сотрудника. */
export interface HREmployeeCard extends HREmployee {
  hired_from: { id: number; application: number; number: string; full_name: string; position: string } | null
  history: HRActivity[]
}

export interface Option<T extends string = string> {
  value: T
  label: string
}

export type ApplicationStatus =
  | 'new' | 'screening' | 'shortlisted' | 'interview_scheduled' | 'interview_done' | 'awaiting_decision'
  | 'next_stage' | 'offer' | 'hired' | 'rejected' | 'withdrawn'
export type ApplicationSource = 'company_site' | 'job_site' | 'social' | 'referral' | 'direct' | 'agency' | 'other'
export type ApplicationChannel = 'public' | 'hr'
export type VacancyStatus = 'draft' | 'published' | 'paused' | 'closed' | 'archived'
export type WorkFormat = 'office' | 'remote' | 'hybrid'
export type EmploymentType = 'full_time' | 'part_time' | 'project' | 'internship'
export type Currency = 'KGS' | 'USD'
export type InterviewStatus = 'scheduled' | 'completed' | 'rescheduled' | 'cancelled' | 'no_show'
export type InterviewFormat = 'in_person' | 'online' | 'phone'
export type InterviewResult = 'passed' | 'failed' | 'undecided'
export type NextStep = 'next_interview' | 'awaiting_decision' | 'offer' | 'reject'

/** `GET /api/v1/hr/meta/` — справочники форм. */
export interface RecruitmentMeta {
  application_statuses: Option<ApplicationStatus>[]
  sources: Option<ApplicationSource>[]
  channels: Option<ApplicationChannel>[]
  vacancy_statuses: Option<VacancyStatus>[]
  work_formats: Option<WorkFormat>[]
  employment_types: Option<EmploymentType>[]
  currencies: Option<Currency>[]
  interview_statuses: Option<InterviewStatus>[]
  interview_formats: Option<InterviewFormat>[]
  interview_results: Option<InterviewResult>[]
  next_steps: Option<NextStep>[]
  hire_roles: HRRoleOption[]
  requestable_roles: Option[]
  people: HRPerson[]
  resume_max_mb: number
  today: string
}

export interface VacancyFields {
  title: string
  slug: string
  department: string
  summary: string
  description: string
  responsibilities: string
  requirements: string
  nice_to_have: string
  conditions: string
  selection_stages: string
  location: string
  work_format: WorkFormat
  employment_type: EmploymentType
  salary_min: number | null
  salary_max: number | null
  salary_currency: Currency
  show_salary: boolean
  closes_on: string | null
  responsible: number | null
}

export type VacancyInput = VacancyFields

export interface Vacancy extends VacancyFields {
  id: number
  status: VacancyStatus
  status_label: string
  work_format_label: string
  employment_type_label: string
  responsible_info: HRPerson | null
  published_at: string | null
  closed_at: string | null
  archived_at: string | null
  applications_count: number
  active_count: number
  new_count: number
  allowed_statuses: Option<VacancyStatus>[]
  missing_for_publishing: string[]
  is_accepting: boolean
  created_at: string
  updated_at: string
}

export interface VacanciesParams {
  status?: string
  search?: string
  responsible?: string
  active?: 'true'
  ordering?: string
  page?: number
  page_size?: number
}

export interface PersonFields {
  last_name: string
  first_name: string
  middle_name: string
  phone: string
  email: string
  city: string
  experience: string
  education: string
  skills: string
  portfolio_url: string
}

export interface Application {
  id: number
  number: string
  candidate: number
  candidate_info: { id: number; full_name: string; phone: string; email: string; erased: boolean }
  vacancy: number | null
  vacancy_info: { id: number; title: string; status: VacancyStatus; status_label: string; slug: string } | null
  position: string
  position_label: string
  channel: ApplicationChannel
  channel_label: string
  source: ApplicationSource
  source_label: string
  source_details: string
  applied_on: string
  responsible: number | null
  responsible_info: HRPerson | null
  status: ApplicationStatus
  status_label: string
  status_changed_at: string
  cover_letter: string
  /** Анкета так, как её отправил кандидат (только для откликов с сайта). */
  submitted_data: Partial<Record<'full_name' | 'phone' | 'email' | keyof PersonFields, string>>
  has_resume: boolean
  resume_name: string
  resume_size: number | null
  consent_at: string | null
  consent_version: string
  needs_duplicate_review: boolean
  hired_user_info: { id: number; username: string; is_active: boolean; role_label: string } | null
  allowed_statuses: Option<ApplicationStatus>[]
  next_interview_at: string | null
  pending_account_request: { id: number; username: string; role: string; role_label: string; created_at: string } | null
  created_at: string
  updated_at: string
}

export interface DuplicateMatch {
  id: number
  full_name: string
  email: string
  phone: string
  same_email: boolean
  same_phone: boolean
  applications: number
}

export interface Candidate extends PersonFields {
  id: number
  full_name: string
  merged_into: number | null
  merged_into_info: { id: number; full_name: string } | null
  erased_at: string | null
  applications: Application[]
  possible_duplicates: DuplicateMatch[]
  created_at: string
  updated_at: string
}

export interface CandidateRow {
  id: number
  full_name: string
  phone: string
  email: string
  city: string
  applications_count: number
  active_count: number
  last_applied_on: string | null
  erased_at: string | null
  merged_into: number | null
  created_at: string
}

export interface ApplicationInput extends Partial<PersonFields> {
  candidate?: number | null
  vacancy: number | null
  position: string
  source: ApplicationSource
  source_details: string
  applied_on: string
  responsible: number | null
  cover_letter: string
  confirm_new?: boolean
}

export interface ApplicationUpdateInput {
  position?: string
  source?: ApplicationSource
  source_details?: string
  applied_on?: string
  responsible?: number | null
  cover_letter?: string
}

export interface ApplicationsParams {
  search?: string
  status?: string
  vacancy?: string
  source?: string
  responsible?: string
  channel?: string
  candidate?: number
  date_from?: string
  date_to?: string
  active?: 'true'
  duplicates?: 'true'
  ordering?: string
  page?: number
  page_size?: number
}

export interface BoardColumn {
  status: ApplicationStatus
  label: string
  count: number
  items: Application[]
}

export interface InternalNote {
  id: number
  candidate: number
  application: number | null
  application_number: string | null
  text: string
  author_info: HRPerson | null
  created_at: string
}

export interface Interview {
  id: number
  application: number
  application_info: { id: number; number: string; status: ApplicationStatus; status_label: string }
  candidate: number
  candidate_info: { id: number; full_name: string }
  vacancy: number | null
  vacancy_info: { id: number | null; title: string } | null
  /** Время офиса с поясом: `2026-10-22T15:00:00+06:00`. */
  scheduled_at: string
  duration_minutes: number
  format: InterviewFormat
  format_label: string
  location: string
  meeting_url: string
  interviewer: number
  interviewer_info: HRPerson
  notes: string
  status: InterviewStatus
  status_label: string
  reschedule_count: number
  rescheduled_to: number | null
  cancel_reason: string
  cancelled_at: string | null
  result: InterviewResult | ''
  result_label: string
  overall_rating: number | null
  skills_rating: number | null
  strengths: string
  concerns: string
  result_comment: string
  next_step: NextStep | ''
  next_step_label: string
  next_step_date: string | null
  completed_at: string | null
  created_at: string
}

export interface InterviewInput {
  /** `YYYY-MM-DDTHH:MM` — время офиса (сервер толкует его в своём поясе). */
  scheduled_at: string
  duration_minutes: number
  format: InterviewFormat
  location: string
  meeting_url: string
  interviewer: number
  notes: string
  confirm?: boolean
}

export interface InterviewsParams {
  date_from?: string
  date_to?: string
  candidate?: number
  application?: number
  interviewer?: string
  vacancy?: string
  status?: string
}

export interface InterviewConflict {
  type: 'candidate' | 'interviewer'
  interview_id: number
  scheduled_at: string
  message: string
}

export interface InterviewResultInput {
  result: InterviewResult
  next_step: NextStep
  overall_rating: number
  skills_rating: number
  strengths: string
  concerns: string
  result_comment: string
  next_step_date: string | null
}

export interface HireInput {
  username: string
  email: string
  first_name: string
  last_name: string
  role: UserRole
  password: string
  password_confirm: string
}

export interface AccountRequestInput {
  role: string
  username: string
  email: string
  first_name: string
  last_name: string
  comment: string
}

export interface AccountRequest {
  id: number
  application: number
  candidate: { id: number; full_name: string }
  role: string
  role_label: string
  username: string
  email: string
  status: 'pending' | 'approved' | 'rejected'
  status_label: string
  created_at: string
}

export interface Reminder {
  kind: 'interview_soon' | 'interview_result' | 'next_step_due' | 'new_waiting' | 'duplicate' | 'vacancy_closing'
    | 'vacancy_expired' | 'account_request'
  level: 'info' | 'warning'
  at: string
  title: string
  candidate?: number
  application?: number
  interview?: number
  vacancy?: number
}

export interface InterviewBrief {
  id: number
  scheduled_at: string
  duration_minutes: number
  status: InterviewStatus
  status_label: string
  format_label: string
  candidate: { id: number; full_name: string }
  application: number
  interviewer: string
  position: string
}

export interface ApplicationBrief {
  id: number
  number: string
  candidate: { id: number; full_name: string }
  status: ApplicationStatus
  status_label: string
  position: string
  source_label: string
  channel: ApplicationChannel
  applied_on: string
  created_at: string
  needs_duplicate_review: boolean
}

/** `GET /api/v1/hr/dashboard/` */
export interface HRDashboard {
  period: { date_from: string; date_to: string }
  employees_active: number
  employees_new: number
  vacancies_open: number
  vacancies_paused: number
  vacancies_draft: number
  vacancies_closed: number
  applications_total: number
  applications_in_progress: number
  applications_today: number
  applications_new: number
  screening: number
  shortlisted: number
  applications_by_status: Record<ApplicationStatus, number>
  interviews_today: number
  interviews_upcoming: number
  awaiting_decision: number
  offers: number
  hired: number
  hired_in_period: number
  rejected: number
  withdrawn: number
  duplicates_to_review: number
  account_requests_pending: number
  recent_applications: ApplicationBrief[]
  upcoming_interviews: InterviewBrief[]
  recent_activity: HRActivity[]
}

export interface ReportFilters {
  vacancy?: string
  source?: string
  responsible?: string
  position?: string
}

export type ReportDefinitions = Record<string, string>

export interface DailyReport {
  date: string
  new_applications: number
  new_by_vacancy: { label: string; count: number }[]
  new_applications_list: ApplicationBrief[]
  passed_screening: number
  interviews_scheduled: number
  interviews_planned: number
  interviews_list: InterviewBrief[]
  interviews_conducted: number
  interviews_rescheduled: number
  interviews_cancelled: number
  interviews_no_show: number
  awaiting_decision_now: number
  decisions: number
  offers: number
  hired: number
  rejected: number
  withdrawn: number
  definitions: ReportDefinitions
}

export interface PeriodReport {
  month: string
  date_from: string
  date_to: string
  new_applications: number
  interviews_conducted: number
  interviews_scheduled: number
  interviews_cancelled: number
  interviews_rescheduled: number
  interviews_no_show: number
  passed_screening: number
  hired: number
  rejected: number
  withdrawn: number
  offers: number
  by_stage: { status: ApplicationStatus; status_label: string; count: number }[]
  funnel: { status: ApplicationStatus; status_label: string; count: number; conversion_percent: number | null }[]
  by_vacancy: { label: string; applications: number; interviews: number; offers: number; hired: number; rejected: number }[]
  by_source: { source: ApplicationSource; label: string; count: number; enough_data: boolean; interview_percent: number | null; hired_percent: number | null }[]
  stage_durations: { status: ApplicationStatus; status_label: string; transitions: number; average_hours: number }[]
  average_days_to_hire: number | null
  vacancies_closed: number
  vacancy_days_to_close: number | null
  definitions: ReportDefinitions
}

export type MonthlyReport = PeriodReport
export type PeriodParams = ReportFilters & { month?: string; date_from?: string; date_to?: string }
