import { apiClient } from '@/api/client'
import type {
  AttendanceLesson,
  AttendanceStatus,
  BulkAction,
  BulkResult,
  Dashboard,
  GenerationSummary,
  GroupCardData,
  GroupCreateInput,
  GroupDetail,
  Options,
  ProgramInput,
  ScheduleData,
  ScholarshipCandidate,
  ScholarshipPeriodRow,
  StudentDetail,
  StudentRow,
  Survey,
  SurveyAnalytics,
  SurveyDetail,
  QuestionType,
} from '@/types/assistant'
import type { Paginated } from '@/types/common'

const BASE = '/assistant'

export interface GroupListParams {
  search?: string
  status?: 'active' | 'archived' | 'all'
  course?: number
  teacher?: number
  page?: number
}

export interface StudentListParams {
  search?: string
  status?: 'all' | 'active' | 'inactive' | 'paused' | 'archived'
  group?: number
  course?: number
  teacher?: number
  no_group?: boolean
  page?: number
  page_size?: number
}

export interface StudentInput {
  first_name: string
  last_name: string
  phone?: string
  parent_phone?: string
  group: number
  enrollment_date?: string | null
}

export interface DeactivateInput {
  reason: string
  event_date?: string | null
  expected_return_date?: string | null
  comment?: string
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

  groups: (params: GroupListParams) => get<Paginated<GroupCardData>>('/groups/', params),
  group: (id: number) => get<GroupDetail>(`/groups/${id}/`),
  createGroup: (body: GroupCreateInput) => post<GroupDetail>('/groups/', body),
  updateGroup: (id: number, body: Partial<Pick<GroupDetail, 'name' | 'start_date' | 'end_date' | 'max_students' | 'description' | 'status'>>) =>
    patch<GroupDetail>(`/groups/${id}/`, body),
  addStudentsToGroup: (id: number, students: number[]) => post<{ added: number; group: GroupDetail }>(`/groups/${id}/students/`, { students }),
  saveProgram: (groupId: number, body: ProgramInput) => post<GroupDetail>(`/groups/${groupId}/programs/`, body),
  generateLessons: (groupId: number) => post<GenerationSummary>(`/groups/${groupId}/generate-lessons/`),

  students: (params: StudentListParams) =>
    get<Paginated<StudentRow>>('/students/', { ...params, no_group: params.no_group ? '1' : undefined }),
  student: (id: number) => get<StudentDetail>(`/students/${id}/`),
  createStudent: (body: StudentInput) => post<StudentDetail>('/students/', body),
  updateStudent: (id: number, body: Partial<StudentInput>) => patch<StudentDetail>(`/students/${id}/`, body),
  deactivate: (id: number, body: DeactivateInput) => post<StudentDetail>(`/students/${id}/deactivate/`, body),
  activate: (id: number, body: ActivateInput) => post<StudentDetail>(`/students/${id}/activate/`, body),
  transfer: (id: number, body: TransferInput) => post<StudentDetail>(`/students/${id}/transfer/`, body),
  bulk: (body: { action: BulkAction; students: number[]; group?: number | null; reason?: string; event_date?: string | null; comment?: string }) =>
    post<BulkResult>('/students/bulk/', body),

  schedule: (params: { start: string; end: string; group?: number; teacher?: number }) => get<ScheduleData>('/schedule/', params),
  moveLesson: (id: number, body: { date: string; start_time: string; end_time: string }) => post(`/lessons/${id}/move/`, body),
  cancelLesson: (id: number, body: { reason: string; reschedule: boolean }) =>
    post<{ id: number; status: string; rescheduled_to: { id: number; date: string; start: string } | null; warning: string }>(
      `/lessons/${id}/cancel/`,
      body,
    ),

  attendance: (params: { date: string; group?: number }) => get<{ date: string; lessons: AttendanceLesson[] }>('/attendance/', params),
  markAttendance: (lessonId: number, entries: { student: number; status: AttendanceStatus; comment?: string }[]) =>
    post<AttendanceLesson>(`/attendance/lessons/${lessonId}/`, entries),

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
