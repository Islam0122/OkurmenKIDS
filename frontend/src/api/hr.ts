import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  Candidate,
  CandidateInput,
  CandidatesParams,
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
  Interview,
  InterviewInput,
  InterviewResultInput,
  InterviewsParams,
  MonthlyReport,
  RecruitmentMeta,
  ReportFilters,
  Vacancy,
  VacancyInput,
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

export const recruitmentApi = {
  meta: () => apiClient.get<RecruitmentMeta>('/hr/meta/').then((r) => r.data),
  dashboard: (params: { date_from?: string; date_to?: string }) =>
    apiClient.get<HRDashboard>('/hr/dashboard/', { params }).then((r) => r.data),

  vacancies: (params: { status?: string; search?: string; page?: number; page_size?: number }) =>
    apiClient.get<Paginated<Vacancy>>('/hr/vacancies/', { params }).then((r) => r.data),
  createVacancy: (payload: VacancyInput) => apiClient.post<Vacancy>('/hr/vacancies/', payload).then((r) => r.data),
  updateVacancy: (id: number, payload: Partial<VacancyInput>) =>
    apiClient.patch<Vacancy>(`/hr/vacancies/${id}/`, payload).then((r) => r.data),

  candidates: (params: CandidatesParams) =>
    apiClient.get<Paginated<Candidate>>('/hr/candidates/', { params }).then((r) => r.data),
  candidate: (id: number) => apiClient.get<Candidate>(`/hr/candidates/${id}/`).then((r) => r.data),
  createCandidate: (payload: CandidateInput) => apiClient.post<Candidate>('/hr/candidates/', payload).then((r) => r.data),
  updateCandidate: (id: number, payload: Partial<CandidateInput>) =>
    apiClient.patch<Candidate>(`/hr/candidates/${id}/`, payload).then((r) => r.data),
  changeStatus: (id: number, status: string, comment: string) =>
    apiClient.post<Candidate>(`/hr/candidates/${id}/status/`, { status, comment }).then((r) => r.data),
  addNote: (id: number, text: string) =>
    apiClient.post<HRActivity>(`/hr/candidates/${id}/notes/`, { text }).then((r) => r.data),
  history: (id: number) => apiClient.get<HRActivity[]>(`/hr/candidates/${id}/history/`).then((r) => r.data),
  hire: (id: number, payload: HireInput) =>
    apiClient.post<Candidate>(`/hr/candidates/${id}/hire/`, payload).then((r) => r.data),

  interviews: (params: InterviewsParams) =>
    apiClient.get<Interview[]>('/hr/interviews/', { params }).then((r) => r.data),
  interview: (id: number) => apiClient.get<Interview>(`/hr/interviews/${id}/`).then((r) => r.data),
  scheduleInterview: (payload: InterviewInput & { candidate: number }) =>
    apiClient.post<Interview>('/hr/interviews/', payload).then((r) => r.data),
  updateInterview: (id: number, payload: Partial<InterviewInput>) =>
    apiClient.patch<Interview>(`/hr/interviews/${id}/`, payload).then((r) => r.data),
  cancelInterview: (id: number, reason: string) =>
    apiClient.post<Interview>(`/hr/interviews/${id}/cancel/`, { reason }).then((r) => r.data),
  recordResult: (id: number, payload: InterviewResultInput) =>
    apiClient.post<Interview>(`/hr/interviews/${id}/result/`, payload).then((r) => r.data),

  daily: (params: ReportFilters & { date?: string }) =>
    apiClient.get<DailyReport>('/hr/reports/daily/', { params }).then((r) => r.data),
  monthly: (params: ReportFilters & { month?: string }) =>
    apiClient.get<MonthlyReport>('/hr/reports/monthly/', { params }).then((r) => r.data),
  exportDaily: (params: ReportFilters & { date?: string }) => saveCsv('/hr/reports/daily/', params, 'hr-daily.csv'),
  exportMonthly: (params: ReportFilters & { month?: string }) =>
    saveCsv('/hr/reports/monthly/', params, 'hr-monthly.csv'),
}
