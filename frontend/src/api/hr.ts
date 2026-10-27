import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  AccountRequest,
  AccountRequestInput,
  Application,
  ApplicationInput,
  ApplicationsParams,
  ApplicationUpdateInput,
  BoardColumn,
  Candidate,
  CandidateRow,
  DailyReport,
  HireInput,
  HRActivity,
  HRDashboard,
  HREmployee,
  HREmployeeCard,
  HREmployeeCreateInput,
  HREmployeeInput,
  HREmployeesParams,
  HRMeta,
  InternalNote,
  Interview,
  InterviewInput,
  InterviewResultInput,
  InterviewsParams,
  PeriodParams,
  PeriodReport,
  PersonFields,
  RecruitmentMeta,
  Reminder,
  ReportFilters,
  VacanciesParams,
  Vacancy,
  VacancyInput,
  VacancyStatus,
} from '@/types/hr'

const BASE = '/hr/employees'

/** CSV-файл под именем из Content-Disposition (JWT-запрос, поэтому не обычная ссылка). */
async function saveCsv(url: string, params: object, fallbackName: string): Promise<void> {
  const response = await apiClient.get<Blob>(url, { params: { ...params, export: 'csv' }, responseType: 'blob' })
  const match = /filename="?([^";]+)"?/.exec(String(response.headers['content-disposition'] ?? ''))
  const href = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = href
  link.download = match?.[1] ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

/** HR-кабинет (backend: apps.users.hr — сотрудники, apps.recruitment — подбор).
 * Все ограничения проверяет сервер. */
export const hrApi = {
  meta: () => apiClient.get<HRMeta>(`${BASE}/meta/`).then((r) => r.data),
  list: (params: HREmployeesParams) => apiClient.get<Paginated<HREmployee>>(`${BASE}/`, { params }).then((r) => r.data),
  employee: (id: number) => apiClient.get<HREmployeeCard>(`${BASE}/${id}/`).then((r) => r.data),
  create: (payload: HREmployeeCreateInput) => apiClient.post<HREmployee>(`${BASE}/`, payload).then((r) => r.data),
  update: (id: number, payload: Partial<HREmployeeInput>) =>
    apiClient.patch<HREmployee>(`${BASE}/${id}/`, payload).then((r) => r.data),
  setPassword: (id: number, password: string, passwordConfirm: string) =>
    apiClient
      .post<HREmployee>(`${BASE}/${id}/set-password/`, { password, password_confirm: passwordConfirm })
      .then((r) => r.data),
  setActive: (id: number, active: boolean) =>
    apiClient.post<HREmployee>(`${BASE}/${id}/${active ? 'activate' : 'deactivate'}/`).then((r) => r.data),
}

/** Файл с сервера по JWT-запросу: скачать или открыть в новой вкладке. */
async function openBlob(url: string, params: object, fallbackName: string, inline: boolean): Promise<void> {
  const response = await apiClient.get<Blob>(url, { params, responseType: 'blob' })
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(String(response.headers['content-disposition'] ?? ''))
  const href = URL.createObjectURL(response.data)
  if (inline) {
    window.open(href, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(href), 60_000)
    return
  }
  const link = document.createElement('a')
  link.href = href
  link.download = match ? decodeURIComponent(match[1]) : fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

export const recruitmentApi = {
  meta: () => apiClient.get<RecruitmentMeta>('/hr/meta/').then((r) => r.data),
  dashboard: (params: { date_from?: string; date_to?: string }) =>
    apiClient.get<HRDashboard>('/hr/dashboard/', { params }).then((r) => r.data),
  reminders: (params: { mine?: 'true' }) =>
    apiClient.get<{ count: number; results: Reminder[] }>('/hr/reminders/', { params }).then((r) => r.data),

  vacancies: (params: VacanciesParams) =>
    apiClient.get<Paginated<Vacancy>>('/hr/vacancies/', { params }).then((r) => r.data),
  vacancy: (id: number) => apiClient.get<Vacancy>(`/hr/vacancies/${id}/`).then((r) => r.data),
  createVacancy: (payload: VacancyInput) => apiClient.post<Vacancy>('/hr/vacancies/', payload).then((r) => r.data),
  updateVacancy: (id: number, payload: Partial<VacancyInput>) =>
    apiClient.patch<Vacancy>(`/hr/vacancies/${id}/`, payload).then((r) => r.data),
  setVacancyStatus: (id: number, status: VacancyStatus) =>
    apiClient.post<Vacancy>(`/hr/vacancies/${id}/status/`, { status }).then((r) => r.data),

  candidates: (params: { search?: string; page?: number; ordering?: string }) =>
    apiClient.get<Paginated<CandidateRow>>('/hr/candidates/', { params }).then((r) => r.data),
  candidate: (id: number) => apiClient.get<Candidate>(`/hr/candidates/${id}/`).then((r) => r.data),
  updateCandidate: (id: number, payload: Partial<PersonFields>) =>
    apiClient.patch<Candidate>(`/hr/candidates/${id}/`, payload).then((r) => r.data),
  notes: (id: number) => apiClient.get<InternalNote[]>(`/hr/candidates/${id}/notes/`).then((r) => r.data),
  addNote: (id: number, text: string, application: number | null) =>
    apiClient.post<InternalNote>(`/hr/candidates/${id}/notes/`, { text, application }).then((r) => r.data),
  history: (id: number) => apiClient.get<HRActivity[]>(`/hr/candidates/${id}/history/`).then((r) => r.data),
  mergeCandidate: (id: number, target: number) =>
    apiClient.post<Candidate>(`/hr/candidates/${id}/merge/`, { target }).then((r) => r.data),
  eraseCandidate: (id: number, reason: string) =>
    apiClient.post<Candidate>(`/hr/candidates/${id}/erase/`, { confirm: true, reason }).then((r) => r.data),

  applications: (params: ApplicationsParams) =>
    apiClient.get<Paginated<Application>>('/hr/applications/', { params }).then((r) => r.data),
  board: (params: ApplicationsParams) =>
    apiClient.get<{ columns: BoardColumn[] }>('/hr/applications/board/', { params }).then((r) => r.data),
  createApplication: (payload: ApplicationInput, resume?: File | null) => {
    if (!resume) return apiClient.post<Application>('/hr/applications/', payload).then((r) => r.data)
    const form = new FormData()
    for (const [key, value] of Object.entries(payload)) {
      if (value !== undefined && value !== null) form.append(key, String(value))
    }
    form.append('resume', resume)
    return apiClient.post<Application>('/hr/applications/', form).then((r) => r.data)
  },
  updateApplication: (id: number, payload: ApplicationUpdateInput) =>
    apiClient.patch<Application>(`/hr/applications/${id}/`, payload).then((r) => r.data),
  changeStatus: (id: number, status: string, comment: string) =>
    apiClient.post<Application>(`/hr/applications/${id}/status/`, { status, comment }).then((r) => r.data),
  notDuplicate: (id: number) => apiClient.post<Application>(`/hr/applications/${id}/not-duplicate/`).then((r) => r.data),
  uploadResume: (id: number, file: File) => {
    const form = new FormData()
    form.append('resume', file)
    return apiClient.post<Application>(`/hr/applications/${id}/resume/`, form).then((r) => r.data)
  },
  /** Резюме — только через API с проверкой прав (без публичной ссылки). */
  openResume: (id: number, inline: boolean) =>
    openBlob(`/hr/applications/${id}/resume/`, inline ? { inline: '1' } : {}, 'resume', inline),
  hire: (id: number, payload: HireInput) =>
    apiClient.post<Application>(`/hr/applications/${id}/hire/`, payload).then((r) => r.data),
  requestAccount: (id: number, payload: AccountRequestInput) =>
    apiClient.post<AccountRequest>(`/hr/applications/${id}/account-request/`, payload).then((r) => r.data),

  interviews: (params: InterviewsParams) =>
    apiClient.get<Interview[]>('/hr/interviews/', { params }).then((r) => r.data),
  interview: (id: number) => apiClient.get<Interview>(`/hr/interviews/${id}/`).then((r) => r.data),
  scheduleInterview: (payload: InterviewInput & { application: number }) =>
    apiClient.post<Interview>('/hr/interviews/', payload).then((r) => r.data),
  updateInterview: (id: number, payload: Partial<InterviewInput>) =>
    apiClient.patch<Interview>(`/hr/interviews/${id}/`, payload).then((r) => r.data),
  cancelInterview: (id: number, reason: string) =>
    apiClient.post<Interview>(`/hr/interviews/${id}/cancel/`, { reason }).then((r) => r.data),
  markNoShow: (id: number, comment: string) =>
    apiClient.post<Interview>(`/hr/interviews/${id}/no-show/`, { comment }).then((r) => r.data),
  recordResult: (id: number, payload: InterviewResultInput) =>
    apiClient.post<Interview>(`/hr/interviews/${id}/result/`, payload).then((r) => r.data),

  daily: (params: ReportFilters & { date?: string }) =>
    apiClient.get<DailyReport>('/hr/reports/daily/', { params }).then((r) => r.data),
  monthly: (params: PeriodParams) =>
    apiClient.get<PeriodReport>('/hr/reports/monthly/', { params }).then((r) => r.data),
  exportDaily: (params: ReportFilters & { date?: string }) => saveCsv('/hr/reports/daily/', params, 'hr-daily.csv'),
  exportMonthly: (params: PeriodParams) => saveCsv('/hr/reports/monthly/', params, 'hr-monthly.csv'),
}
