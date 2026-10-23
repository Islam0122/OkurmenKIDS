import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  AdjustPayload,
  Adjustment,
  AdminMeta,
  AttendanceSettings,
  DayRow,
  EmployeeCard,
  ManualSessionPayload,
  MarkPayload,
  MarkResult,
  MonthStats,
  MyStatus,
  OfficeInfo,
  OfficeLocation,
  OfficeLocationInput,
  Overview,
  RecordsParams,
  WorkSchedule,
  WorkScheduleInput,
  WorkSession,
} from '@/types/staffAttendance'

const BASE = '/staff-attendance'

/** Сохранить ответ-файл под именем из Content-Disposition (JWT-запрос,
 * поэтому не обычная ссылка). */
async function saveBlob(url: string, params: object | undefined, fallbackName: string, type: string): Promise<string> {
  const response = await apiClient.get<Blob>(url, { params, responseType: 'blob' })
  const match = /filename="?([^";]+)"?/.exec(String(response.headers['content-disposition'] ?? ''))
  const name = match?.[1] ?? fallbackName
  const href = URL.createObjectURL(new Blob([response.data], { type }))
  const link = document.createElement('a')
  link.href = href
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
  return name
}

/** Учёт прихода и ухода сотрудников. Личные методы (`me/…`) всегда работают
 * только с текущим пользователем — id сотрудника в них не передаётся. */
export const staffAttendanceApi = {
  myStatus: (): Promise<MyStatus> => apiClient.get<MyStatus>(`${BASE}/me/status/`).then((r) => r.data),

  verifyOffice: (code: string): Promise<OfficeInfo> =>
    apiClient.get<OfficeInfo>(`${BASE}/me/locations/${encodeURIComponent(code)}/`).then((r) => r.data),

  checkIn: (payload: MarkPayload): Promise<MarkResult> =>
    apiClient.post<MarkResult>(`${BASE}/me/check-in/`, payload).then((r) => r.data),

  checkOut: (payload: MarkPayload): Promise<MarkResult> =>
    apiClient.post<MarkResult>(`${BASE}/me/check-out/`, payload).then((r) => r.data),

  myHistory: (params: { date_from?: string; date_to?: string; page?: number }): Promise<Paginated<WorkSession>> =>
    apiClient.get<Paginated<WorkSession>>(`${BASE}/me/history/`, { params }).then((r) => r.data),

  myStats: (month: string): Promise<MonthStats> =>
    apiClient.get<MonthStats>(`${BASE}/me/stats/`, { params: { month } }).then((r) => r.data),

  meta: (): Promise<AdminMeta> => apiClient.get<AdminMeta>(`${BASE}/admin/meta/`).then((r) => r.data),

  overview: (params: RecordsParams): Promise<Overview> =>
    apiClient.get<Overview>(`${BASE}/admin/overview/`, { params }).then((r) => r.data),

  records: (params: RecordsParams): Promise<Paginated<DayRow>> =>
    apiClient.get<Paginated<DayRow>>(`${BASE}/admin/records/`, { params }).then((r) => r.data),

  exportCsv: (params: RecordsParams): Promise<string> =>
    saveBlob(`${BASE}/admin/export/`, params, 'staff-attendance.csv', 'text/csv;charset=utf-8'),

  employee: (id: number, params: { date_from?: string; date_to?: string }): Promise<EmployeeCard> =>
    apiClient.get<EmployeeCard>(`${BASE}/admin/employees/${id}/`, { params }).then((r) => r.data),

  adjust: (sessionId: number, payload: AdjustPayload): Promise<Adjustment> =>
    apiClient.post<Adjustment>(`${BASE}/admin/sessions/${sessionId}/adjust/`, payload).then((r) => r.data),

  createManual: (payload: ManualSessionPayload): Promise<Adjustment> =>
    apiClient.post<Adjustment>(`${BASE}/admin/sessions/`, payload).then((r) => r.data),

  locations: (): Promise<OfficeLocation[]> =>
    apiClient.get<OfficeLocation[]>(`${BASE}/admin/locations/`).then((r) => r.data),

  createLocation: (payload: OfficeLocationInput): Promise<OfficeLocation> =>
    apiClient.post<OfficeLocation>(`${BASE}/admin/locations/`, payload).then((r) => r.data),

  updateLocation: (id: number, payload: Partial<OfficeLocationInput>): Promise<OfficeLocation> =>
    apiClient.patch<OfficeLocation>(`${BASE}/admin/locations/${id}/`, payload).then((r) => r.data),

  /** SVG QR-кода офиса (загружается с JWT и показывается как blob-URL). */
  locationQrSvg: (id: number): Promise<string> =>
    apiClient.get<string>(`${BASE}/admin/locations/${id}/qr.svg`, { responseType: 'text' }).then((r) => r.data),

  settings: (): Promise<AttendanceSettings> =>
    apiClient.get<AttendanceSettings>(`${BASE}/admin/settings/`).then((r) => r.data),

  updateSettings: (payload: Partial<AttendanceSettings>): Promise<AttendanceSettings> =>
    apiClient.patch<AttendanceSettings>(`${BASE}/admin/settings/`, payload).then((r) => r.data),

  schedules: (): Promise<WorkSchedule[]> =>
    apiClient.get<WorkSchedule[]>(`${BASE}/admin/schedules/`).then((r) => r.data),

  saveSchedule: (userId: number, payload: WorkScheduleInput): Promise<WorkSchedule> =>
    apiClient.put<WorkSchedule>(`${BASE}/admin/employees/${userId}/schedule/`, payload).then((r) => r.data),

  deleteSchedule: (userId: number): Promise<void> =>
    apiClient.delete(`${BASE}/admin/employees/${userId}/schedule/`).then(() => undefined),
}
