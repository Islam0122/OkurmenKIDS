import { apiClient } from '@/api/client'
import type {
  AttendanceLesson,
  BulkAction,
  BulkResult,
  Dashboard,
  GenerationSummary,
  GroupCardData,
  GroupCreateInput,
  GroupDetail,
  Options,
  SearchResults,
  ControlOverview,
  ControlProfile,
  MonthlyReport,
  ReportFilters,
  GroupAttendance,
  GroupHomework,
  HomeworkDetail,
  LessonDetail,
  ProgramInput,
  ScheduleData,
  ScholarshipCandidate,
  ScholarshipPeriodRow,
  AccountDetail,
  FamilyAccount,
  StudentDetail,
  StudentRow,
  Survey,
  SurveyAnalytics,
  SurveyDetail,
  QuestionType,
} from '@/types/assistant'
import type { SubjectStartOverview } from '@/types/academy'
import type { Paginated } from '@/types/common'

const BASE = '/assistant'

export interface GroupListParams {
  search?: string
  status?: 'active' | 'archived' | 'all'
  course?: number
  teacher?: number
  day?: string
  page?: number
  page_size?: number
}

/** Filters of a group's attendance / homework tabs. */
export interface RecordFilters {
  period?: 'today' | 'week' | 'month' | 'all' | 'custom'
  start?: string
  end?: string
  student?: number
  teacher?: number
  status?: string
}

export interface StudentListParams {
  search?: string
  status?: 'all' | 'active' | 'inactive' | 'paused' | 'archived'
  group?: number
  course?: number
  teacher?: number
  no_group?: boolean
  branch?: number
  account?: 'none' | 'pending' | 'active' | 'disabled'
  page?: number
  page_size?: number
}

export interface StudentInput {
  first_name: string
  last_name: string
  phone?: string
  parent_phone?: string
  parent_name?: string
  birth_date?: string | null
  branch?: number | null
  group: number
  enrollment_date?: string | null
  /** Кабинет ученика и родителя: создать аккаунт (по умолчанию) … */
  create_account?: boolean
  login?: string
  /** … или привязать к аккаунту брата / сестры. */
  link_account?: number | null
}

export interface AccountCheck {
  suggested_login: string
  family_accounts: FamilyAccount[]
}

export interface DeactivateInput {
  reason: string
  event_date?: string | null
  expected_return_date?: string | null
  comment?: string
}

/** Окно деактивации: кто уходит и его деньги по договорам (как у бухгалтерии). */
export interface DeactivationPreview {
  id: number
  full_name: string
  status: string
  status_display: string
  group: { id: number; name: string } | null
  course: string | null
  subjects: string[]
  enrollment_date: string | null
  contracts: { id: number; number: number; subject: string | null; plan: string; status: string; status_display: string; start_date: string }[]
  finance: {
    contract_price: string | null
    invoiced: string
    paid: string
    discount: string
    adjusted: string
    debt: string
    due_now: string
    overpayment: string
    contracts_count: number
    has_debt: boolean
  }
  on_stop: { live_contracts: number; voided_on_stop: string }
}

export interface ActivateInput {
  group?: number | null
  event_date?: string | null
  comment?: string
}

export interface TransferInput {
  group: number
  event_date?: string | null
  comment?: string
}

const get = <T>(url: string, params?: object) => apiClient.get<T>(`${BASE}${url}`, { params }).then((r) => r.data)
const post = <T>(url: string, body?: unknown) => apiClient.post<T>(`${BASE}${url}`, body).then((r) => r.data)
const patch = <T>(url: string, body?: unknown) => apiClient.patch<T>(`${BASE}${url}`, body).then((r) => r.data)

export const assistantApi = {
  dashboard: () => get<Dashboard>('/dashboard/'),
  options: () => get<Options>('/options/'),
  search: (q: string) => get<SearchResults>('/search/', { q }),

  groups: (params: GroupListParams) => get<Paginated<GroupCardData>>('/groups/', params),
  group: (id: number) => get<GroupDetail>(`/groups/${id}/`),
  createGroup: (body: GroupCreateInput) => post<GroupDetail>('/groups/', body),
  updateGroup: (id: number, body: Partial<Pick<GroupDetail, 'name' | 'start_date' | 'end_date' | 'max_students' | 'description' | 'status'>>) =>
    patch<GroupDetail>(`/groups/${id}/`, body),
  addStudentsToGroup: (id: number, students: number[]) => post<{ added: number; group: GroupDetail }>(`/groups/${id}/students/`, { students }),
  saveProgram: (groupId: number, body: ProgramInput) => post<GroupDetail>(`/groups/${groupId}/programs/`, body),
  subjectStartDates: (groupId: number) => get<SubjectStartOverview>(`/groups/${groupId}/subject-start-dates/`),
  saveSubjectStartDate: (groupId: number, subjectId: number, startDate: string) =>
    patch<SubjectStartOverview>(`/groups/${groupId}/subject-start-dates/${subjectId}/`, { start_date: startDate }),
  generateLessons: (groupId: number) => post<GenerationSummary>(`/groups/${groupId}/generate-lessons/`),

  students: (params: StudentListParams) =>
    get<Paginated<StudentRow>>('/students/', { ...params, no_group: params.no_group ? '1' : undefined }),
  student: (id: number) => get<StudentDetail>(`/students/${id}/`),
  createStudent: (body: StudentInput) => post<StudentDetail>('/students/', body),
  updateStudent: (id: number, body: Partial<StudentInput>) => patch<StudentDetail>(`/students/${id}/`, body),
  deactivationPreview: (id: number) => get<DeactivationPreview>(`/students/${id}/deactivation-preview/`),
  deactivate: (id: number, body: DeactivateInput) => post<StudentDetail>(`/students/${id}/deactivate/`, body),
  activate: (id: number, body: ActivateInput) => post<StudentDetail>(`/students/${id}/activate/`, body),
  transfer: (id: number, body: TransferInput) => post<StudentDetail>(`/students/${id}/transfer/`, body),
  accountCheck: (params: { first_name: string; last_name: string; parent_phone: string }) =>
    get<AccountCheck>('/students/account-check/', params),
  exportStudents: (params: StudentListParams, format: 'xlsx' | 'csv' = 'xlsx') =>
    apiClient
      .get<Blob>(`${BASE}/students/export/`, {
        params: { ...params, no_group: params.no_group ? '1' : undefined, page: undefined, export_format: format },
        responseType: 'blob',
      })
      .then((r) => r.data),
  uploadPhoto: (id: number, file: File) => {
    const form = new FormData()
    form.append('photo', file)
    return post<StudentDetail>(`/students/${id}/photo/`, form)
  },
  deletePhoto: (id: number) => apiClient.delete<StudentDetail>(`${BASE}/students/${id}/photo/`).then((r) => r.data),
  account: (id: number) => get<AccountDetail | null>(`/students/${id}/account/`),
  provisionAccount: (id: number, login?: string) => post<StudentDetail>(`/students/${id}/account/`, { login: login ?? '' }),
  resetPassword: (id: number) => post<StudentDetail>(`/students/${id}/account/reset-password/`),
  changeLogin: (id: number, login: string) => patch<StudentDetail>(`/students/${id}/account/login/`, { login }),
  setAccountActive: (id: number, value: boolean) => post<StudentDetail>(`/students/${id}/account/active/`, { value }),
  setPaymentsVisible: (id: number, value: boolean) => post<StudentDetail>(`/students/${id}/account/payments/`, { value }),
  linkAccount: (id: number, account: number) => post<StudentDetail>(`/students/${id}/account/link/`, { account }),
  unlinkAccount: (id: number) => post<StudentDetail>(`/students/${id}/account/unlink/`),
  bulk: (body: { action: BulkAction; students: number[]; group?: number | null; reason?: string; event_date?: string | null; comment?: string }) =>
    post<BulkResult>('/students/bulk/', body),

  schedule: (params: { start: string; end: string; group?: number; teacher?: number; course?: number; day?: string }) => get<ScheduleData>('/schedule/', params),
  moveLesson: (id: number, body: { date: string; start_time: string; end_time: string }) => post(`/lessons/${id}/move/`, body),
  cancelLesson: (id: number, body: { reason: string; reschedule: boolean }) =>
    post<{ id: number; status: string; rescheduled_to: { id: number; date: string; start: string } | null; warning: string }>(
      `/lessons/${id}/cancel/`,
      body,
    ),

  attendance: (params: { date: string; group?: number; unmarked?: boolean }) => get<{ date: string; lessons: AttendanceLesson[] }>('/attendance/', params),

  groupAttendance: (id: number, params: RecordFilters) => get<GroupAttendance>(`/groups/${id}/attendance/`, params),
  groupHomework: (id: number, params: RecordFilters) => get<GroupHomework>(`/groups/${id}/homework/`, params),
  lesson: (id: number) => get<LessonDetail>(`/lessons/${id}/`),
  homework: (id: number) => get<HomeworkDetail>(`/homework/${id}/`),
  control: (params: { period?: string; group?: number; category?: string; sort?: string }) => get<ControlOverview>('/control/', params),
  controlStudent: (id: number, period: string) => get<ControlProfile>(`/control/students/${id}/`, { period }),
  monthlyReport: (year: number, month: number, filters: Partial<ReportFilters> = {}) =>
    get<MonthlyReport>('/reports/monthly/', { year, month, ...filters }),
  /** The same report as a PDF. JWT auth like every call — a plain `<a href>` would 401 — so it is fetched as a blob. */
  downloadMonthlyReportPdf: async (year: number, month: number, filters: Partial<ReportFilters> = {}): Promise<void> => {
    const response = await apiClient.get<Blob>(`${BASE}/reports/monthly/${year}/${month}/pdf/`, { params: filters, responseType: 'blob' })
    const match = /filename="?([^";]+)"?/.exec(String(response.headers['content-disposition'] ?? ''))
    const href = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    const link = document.createElement('a')
    link.href = href
    link.download = match?.[1] ?? `monthly_report_${year}_${month}.pdf`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(href)
  },

  scholarships: () => get<{ award_days: number[]; pending: number; periods: ScholarshipPeriodRow[] }>('/scholarships/'),
  generateScholarship: (body: { award_day?: number | null }) =>
    post<{ created: boolean; period: ScholarshipPeriodRow }>('/scholarships/generate/', body),
  scholarshipCandidates: (periodId: number) => get<ScholarshipCandidate[]>(`/scholarships/periods/${periodId}/awards/`),
  addScholarshipAward: (periodId: number, evaluation: number) => post<ScholarshipPeriodRow>(`/scholarships/periods/${periodId}/awards/`, { evaluation }),
}

/** Surveys reuse the existing feedback API (backend: apps.feedback, Admin + Assistant). */
export interface SurveyInput {
  title: string
  description?: string
  audience: 'parent' | 'student'
  visibility_mode: 'open' | 'anonymous' | 'both'
  group?: number | null
}

export interface QuestionInput {
  text: string
  question_type: QuestionType
  is_required: boolean
  options?: { text: string }[]
}

export const surveysApi = {
  list: (params: { status?: string; group?: number; search?: string; page?: number }) =>
    apiClient.get<Paginated<Survey>>('/feedback/surveys/', { params: { ordering: '-created_at', ...params } }).then((r) => r.data),
  get: (id: number) => apiClient.get<SurveyDetail>(`/feedback/surveys/${id}/`).then((r) => r.data),
  create: (body: SurveyInput) => apiClient.post<Survey>('/feedback/surveys/', body).then((r) => r.data),
  addQuestion: (id: number, body: QuestionInput) => apiClient.post(`/feedback/surveys/${id}/questions/`, body).then((r) => r.data),
  removeQuestion: (questionId: number) => apiClient.delete(`/feedback/questions/${questionId}/`),
  publish: (id: number) => apiClient.post<SurveyDetail>(`/feedback/surveys/${id}/publish/`).then((r) => r.data),
  close: (id: number) => apiClient.post<SurveyDetail>(`/feedback/surveys/${id}/close/`).then((r) => r.data),
  reopen: (id: number) => apiClient.post<SurveyDetail>(`/feedback/surveys/${id}/reopen/`).then((r) => r.data),
  analytics: (id: number) => apiClient.get<SurveyAnalytics>(`/feedback/surveys/${id}/analytics/`).then((r) => r.data),
}
