import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  Dashboard,
  DailyControl,
  DepartmentDetail,
  DepartmentRow,
  EmployeeProfile,
  EmployeeRow,
  HeadOfSalesResponse,
  HrResponse,
  Issue,
  IssueDetail,
  IssuesParams,
  KpiOverview,
  KpiTarget,
  KpiTargetInput,
  MarketingResponse,
  MyTasks,
  Notification,
  OpsFiltersParams,
  OpsMeta,
  OpsSettings,
  ProblemStudent,
  Recurrence,
  RecurrenceInput,
  ReportsResponse,
  SalesResponse,
  StaffAttendanceResponse,
  StudentsOverview,
  TaskDetail,
  TaskInput,
  TaskListItem,
  TasksMeta,
  TasksParams,
  TeamLeadRow,
  AssistantRow,
  TrainerDetail,
  TrainersResponse,
  WorkReport,
  WorkReportsMeta,
  ActivityEvent,
  FiltersEcho,
  Priority,
} from '@/types/operations'

const OPS = '/operations'
type Params = OpsFiltersParams & Record<string, string | number | undefined>

/** Кабинет операционного директора (backend: apps.operations, CanOversee).
 * Все права проверяет сервер. */
export const operationsApi = {
  meta: () => apiClient.get<OpsMeta>(`${OPS}/meta/`).then((r) => r.data),
  dashboard: (params: Params) => apiClient.get<Dashboard>(`${OPS}/dashboard/`, { params }).then((r) => r.data),
  departments: (params: Params) =>
    apiClient.get<{ departments: DepartmentRow[] }>(`${OPS}/departments/`, { params }).then((r) => r.data),
  department: (key: string, params: Params) =>
    apiClient.get<DepartmentDetail>(`${OPS}/departments/${key}/`, { params }).then((r) => r.data),
  employees: (params: Params) =>
    apiClient.get<{ filters: FiltersEcho; employees: EmployeeRow[]; total: number }>(`${OPS}/employees/`, { params }).then((r) => r.data),
  employee: (id: number, params: Params) =>
    apiClient.get<EmployeeProfile>(`${OPS}/employees/${id}/`, { params }).then((r) => r.data),
  trainers: (params: Params) => apiClient.get<TrainersResponse>(`${OPS}/trainers/`, { params }).then((r) => r.data),
  trainer: (id: number, params: Params) =>
    apiClient.get<TrainerDetail>(`${OPS}/trainers/${id}/`, { params }).then((r) => r.data),
  teamLeads: (params: Params) =>
    apiClient.get<{ team_leads: TeamLeadRow[]; assistants: AssistantRow[] }>(`${OPS}/team-leads/`, { params }).then((r) => r.data),
  problemStudents: (params: Params) =>
    apiClient
      .get<{ students: ProblemStudent[]; summary: StudentsOverview; groups: { id: number; name: string; kpi: number | null; attendance_rate: number | null; reason: string }[] }>(
        `${OPS}/students/problems/`, { params })
      .then((r) => r.data),
  sales: (params: Params) => apiClient.get<SalesResponse>(`${OPS}/sales/`, { params }).then((r) => r.data),
  headOfSales: (params: Params) => apiClient.get<HeadOfSalesResponse>(`${OPS}/sales/head/`, { params }).then((r) => r.data),
  marketing: (params: Params) => apiClient.get<MarketingResponse>(`${OPS}/marketing/`, { params }).then((r) => r.data),
  hr: (params: Params) => apiClient.get<HrResponse>(`${OPS}/hr/`, { params }).then((r) => r.data),
  attendance: (params: Params) =>
    apiClient.get<StaffAttendanceResponse>(`${OPS}/attendance/`, { params }).then((r) => r.data),
  daily: (date?: string) => apiClient.get<DailyControl>(`${OPS}/daily/`, { params: { date } }).then((r) => r.data),
  kpi: (params: Params) => apiClient.get<KpiOverview>(`${OPS}/kpi/`, { params }).then((r) => r.data),
  kpiHistory: (params: Params) =>
    apiClient
      .get<{ history: { start: string; end: string; actual: number | null; target: number | null; achievement: number | null }[] }>(
        `${OPS}/kpi/history/`, { params })
      .then((r) => r.data),
  targets: (params: Record<string, string | undefined>) =>
    apiClient.get<Paginated<KpiTarget>>(`${OPS}/kpi/targets/`, { params: { page_size: 200, ...params } }).then((r) => r.data),
  saveTarget: (id: number | null, body: KpiTargetInput) =>
    (id === null ? apiClient.post<KpiTarget>(`${OPS}/kpi/targets/`, body) : apiClient.patch<KpiTarget>(`${OPS}/kpi/targets/${id}/`, body)).then((r) => r.data),
  deleteTarget: (id: number) => apiClient.delete(`${OPS}/kpi/targets/${id}/`).then(() => undefined),
  reports: (params: Params) => apiClient.get<ReportsResponse>(`${OPS}/reports/`, { params }).then((r) => r.data),
  exportReport: async (params: Params) => {
    const response = await apiClient.get<Blob>(`${OPS}/reports/export/`, { params, responseType: 'blob' })
    const disposition = String(response.headers['content-disposition'] ?? '')
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'report'
    return { blob: response.data, name }
  },
  activity: (department?: string) =>
    apiClient.get<{ events: ActivityEvent[] }>(`${OPS}/activity/`, { params: { department } }).then((r) => r.data),
  issues: (params: IssuesParams) =>
    apiClient
      .get<Paginated<Issue> & { summary: { active: number; high: number; repeated: number; by_kind: Record<string, number> } }>(
        `${OPS}/issues/`, { params })
      .then((r) => r.data),
  issue: (id: number) => apiClient.get<IssueDetail>(`${OPS}/issues/${id}/`).then((r) => r.data),
  createIssue: (body: { title: string; description?: string; department: string; priority: Priority; responsible?: number | null }) =>
    apiClient.post<IssueDetail>(`${OPS}/issues/`, body).then((r) => r.data),
  issueStatus: (id: number, status: string, comment?: string) =>
    apiClient.post<IssueDetail>(`${OPS}/issues/${id}/status/`, { status, comment }).then((r) => r.data),
  issueAssign: (id: number, responsible: number | null) =>
    apiClient.post<IssueDetail>(`${OPS}/issues/${id}/assign/`, { responsible }).then((r) => r.data),
  issueComment: (id: number, text: string) => apiClient.post(`${OPS}/issues/${id}/comment/`, { text }).then((r) => r.data),
  scan: () => apiClient.post<Record<string, unknown>>(`${OPS}/scan/`).then((r) => r.data),
  settings: () => apiClient.get<OpsSettings>(`${OPS}/settings/`).then((r) => r.data),
  saveSettings: (body: Partial<OpsSettings>) => apiClient.patch<OpsSettings>(`${OPS}/settings/`, body).then((r) => r.data),
}

/** Задачи, отчёты и уведомления каждого сотрудника (чужие записи сервер не отдаёт). */
export const tasksApi = {
  meta: () => apiClient.get<TasksMeta>('/tasks/meta/').then((r) => r.data),
  list: (params: TasksParams) => apiClient.get<Paginated<TaskListItem>>('/tasks/', { params }).then((r) => r.data),
  my: () => apiClient.get<MyTasks>('/tasks/my/').then((r) => r.data),
  get: (id: number) => apiClient.get<TaskDetail>(`/tasks/${id}/`).then((r) => r.data),
  create: (body: TaskInput) => apiClient.post<TaskDetail>('/tasks/', body).then((r) => r.data),
  update: (id: number, body: Partial<TaskInput>) => apiClient.patch<TaskDetail>(`/tasks/${id}/`, body).then((r) => r.data),
  act: (id: number, action: string, comment?: string) =>
    apiClient.post<TaskDetail>(`/tasks/${id}/${action}/`, { comment }).then((r) => r.data),
  addChecklist: (id: number, text: string) => apiClient.post(`/tasks/${id}/checklist/`, { text }).then((r) => r.data),
  toggleChecklist: (id: number, itemId: number, isDone: boolean) =>
    apiClient.patch(`/tasks/${id}/checklist/${itemId}/`, { is_done: isDone }).then((r) => r.data),
  comment: (id: number, text: string) => apiClient.post(`/tasks/${id}/comments/`, { text }).then((r) => r.data),
  upload: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post(`/tasks/${id}/attachments/`, form).then((r) => r.data)
  },
  deleteAttachment: (id: number, attachmentId: number) =>
    apiClient.delete(`/tasks/${id}/attachments/${attachmentId}/`).then(() => undefined),
  download: async (url: string) => {
    // download_url — полный путь API; клиент сам добавляет базовый адрес.
    const response = await apiClient.get<Blob>(url.replace(/^\/api\/v1/, ''), { responseType: 'blob' })
    return response.data
  },
  recurrences: () => apiClient.get<Paginated<Recurrence>>('/tasks/recurrences/', { params: { page_size: 200 } }).then((r) => r.data),
  saveRecurrence: (id: number | null, body: RecurrenceInput) =>
    (id === null ? apiClient.post<Recurrence>('/tasks/recurrences/', body) : apiClient.patch<Recurrence>(`/tasks/recurrences/${id}/`, body)).then((r) => r.data),
  stopRecurrence: (id: number) => apiClient.delete(`/tasks/recurrences/${id}/`).then(() => undefined),
}

export const workReportsApi = {
  meta: () => apiClient.get<WorkReportsMeta>('/work-reports/meta/').then((r) => r.data),
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<Paginated<WorkReport>>('/work-reports/', { params }).then((r) => r.data),
  save: (id: number | null, body: Partial<WorkReport>) =>
    (id === null ? apiClient.post<WorkReport>('/work-reports/', body) : apiClient.patch<WorkReport>(`/work-reports/${id}/`, body)).then((r) => r.data),
  submit: (id: number) => apiClient.post<WorkReport>(`/work-reports/${id}/submit/`).then((r) => r.data),
  review: (id: number, decision: 'accept' | 'return', comment?: string) =>
    apiClient.post<WorkReport>(`/work-reports/${id}/review/`, { decision, comment }).then((r) => r.data),
}

export const notificationsApi = {
  list: (params: { unread?: '1'; page?: number }) =>
    apiClient.get<Paginated<Notification>>('/notifications/', { params }).then((r) => r.data),
  unreadCount: () => apiClient.get<{ count: number }>('/notifications/unread-count/').then((r) => r.data),
  read: (id: number) => apiClient.post<Notification>(`/notifications/${id}/read/`).then((r) => r.data),
  readAll: () => apiClient.post('/notifications/read-all/').then((r) => r.data),
}
