import type { StaffOnlyRole } from '@/types/auth'

/** `apps.users.hr.HREmployeeSerializer` — пароль никогда не возвращается. */
export interface HREmployee {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  role: StaffOnlyRole
  role_label: string
  is_active: boolean
  created_at: string
  last_login: string | null
}

export interface HRRoleOption {
  value: StaffOnlyRole
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
  role: StaffOnlyRole
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
  employee: { id: number; full_name: string } | null
  from_status: string
  to_status: string
}

/** `GET /api/v1/hr/employees/:id/` — карточка сотрудника. */
export interface HREmployeeCard extends HREmployee {
  hired_from: { id: number; full_name: string; position: string } | null
  history: HRActivity[]
}

export interface Option<T extends string = string> {
  value: T
  label: string
}

export type CandidateStatus =
  | 'new' | 'contacted' | 'interview_scheduled' | 'interview_done' | 'awaiting_decision' | 'offer' | 'hired'
  | 'rejected' | 'withdrawn'
export type CandidateSource = 'job_site' | 'company_site' | 'social' | 'referral' | 'direct' | 'agency' | 'other'
export type VacancyStatus = 'open' | 'paused' | 'closed'
export type InterviewStatus = 'scheduled' | 'completed' | 'cancelled'
export type InterviewFormat = 'in_person' | 'online' | 'phone'
export type InterviewResult = 'passed' | 'failed' | 'undecided'
export type NextStep = 'next_interview' | 'awaiting_decision' | 'offer' | 'reject'

/** `GET /api/v1/hr/meta/` — справочники форм. */
export interface RecruitmentMeta {
  candidate_statuses: Option<CandidateStatus>[]
  sources: Option<CandidateSource>[]
  vacancy_statuses: Option<VacancyStatus>[]
  interview_statuses: Option<InterviewStatus>[]
  interview_formats: Option<InterviewFormat>[]
  interview_results: Option<InterviewResult>[]
  next_steps: Option<NextStep>[]
  people: HRPerson[]
  today: string
}

export interface Vacancy {
  id: number
  title: string
  description: string
  department: string
  status: VacancyStatus
  status_label: string
  responsible: number | null
  responsible_info: HRPerson | null
  candidates_count: number
  created_at: string
  updated_at: string
}

export interface VacancyInput {
  title: string
  description: string
  department: string
  status: VacancyStatus
  responsible: number | null
}

export interface Candidate {
  id: number
  last_name: string
  first_name: string
  middle_name: string
  full_name: string
  phone: string
  email: string
  vacancy: number | null
  vacancy_info: { id: number; title: string; status: VacancyStatus } | null
  position: string
  position_label: string
  source: CandidateSource
  source_label: string
  source_details: string
  added_on: string
  responsible: number | null
  responsible_info: HRPerson | null
  notes: string
  status: CandidateStatus
  status_label: string
  status_changed_at: string
  hired_user_info: { id: number; username: string; is_active: boolean } | null
  allowed_statuses: Option<CandidateStatus>[]
  next_interview_at: string | null
  created_at: string
  updated_at: string
}

export interface CandidateInput {
  last_name: string
  first_name: string
  middle_name: string
  phone: string
  email: string
  vacancy: number | null
  position: string
  source: CandidateSource
  source_details: string
  added_on: string
  responsible: number | null
  notes: string
}

export interface CandidatesParams {
  search?: string
  status?: string
  vacancy?: string
  source?: string
  responsible?: string
  position?: string
  active?: 'true'
  ordering?: string
  page?: number
  page_size?: number
}

export interface Interview {
  id: number
  candidate: number
  candidate_info: { id: number; full_name: string; status: CandidateStatus; status_label: string }
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
  cancel_reason: string
  cancelled_at: string | null
  result: InterviewResult | ''
  result_label: string
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
  result_comment: string
  next_step_date: string | null
}

export interface HireInput {
  username: string
  email: string
  first_name: string
  last_name: string
  role: StaffOnlyRole
  password: string
  password_confirm: string
}

export interface InterviewBrief {
  id: number
  scheduled_at: string
  duration_minutes: number
  status: InterviewStatus
  status_label: string
  format_label: string
  candidate: { id: number; full_name: string }
  interviewer: string
  position: string
}

export interface CandidateBrief {
  id: number
  full_name: string
  status: CandidateStatus
  status_label: string
  position: string
  source_label: string
  added_on: string
}

/** `GET /api/v1/hr/dashboard/` */
export interface HRDashboard {
  period: { date_from: string; date_to: string }
  employees_active: number
  employees_new: number
  candidates_total: number
  candidates_in_progress: number
  candidates_by_status: Record<CandidateStatus, number>
  interviews_scheduled: number
  interviews_today: number
  awaiting_decision: number
  interview_passed: number
  offers: number
  hired: number
  rejected: number
  withdrawn: number
  vacancies_open: number
  upcoming_interviews: InterviewBrief[]
  recent_activity: HRActivity[]
}

export interface ReportFilters {
  vacancy?: string
  source?: string
  responsible?: string
  position?: string
}

export interface DailyReport {
  date: string
  new_candidates: number
  new_candidates_list: CandidateBrief[]
  interviews_planned: number
  interviews_list: InterviewBrief[]
  interviews_conducted: number
  interviews_rescheduled: number
  interviews_cancelled: number
  awaiting_decision_now: number
  decisions: number
  offers: number
  hired: number
  rejected: number
  withdrawn: number
}

export interface MonthlyReport {
  month: string
  new_candidates: number
  interviews_conducted: number
  interviews_cancelled: number
  interviews_rescheduled: number
  hired: number
  rejected: number
  withdrawn: number
  offers: number
  by_stage: { status: CandidateStatus; status_label: string; count: number }[]
  funnel: { status: CandidateStatus; status_label: string; count: number; conversion_percent: number | null }[]
  by_vacancy: { label: string; count: number }[]
  by_source: { label: string; count: number }[]
  stage_durations: { status: CandidateStatus; status_label: string; transitions: number; average_hours: number }[]
  average_days_to_hire: number | null
}
