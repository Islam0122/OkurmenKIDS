import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  AchievementsOverview,
  FeedbackItem,
  HomeworkState,
  MonthlyReport,
  NextHomework,
  PortalAttendanceMonth,
  PortalDashboard,
  PortalHomework,
  PortalHomeworkDetail,
  PortalLesson,
  PortalMe,
  PortalNotification,
  PortalFinance,
  PortalReceiptDetail,
  PortalReceipt,
  PortalInvoice,
  PortalTransaction,
} from '@/types/studentPortal'

const BASE = '/portal'
const get = <T>(url: string, params?: object) => apiClient.get<T>(`${BASE}${url}`, { params }).then((r) => r.data)
const post = <T>(url: string, body?: unknown) => apiClient.post<T>(`${BASE}${url}`, body).then((r) => r.data)
const s = (id: number) => `/students/${id}`

export type TransactionFilter = 'all' | 'completed' | 'refunded' | 'cancelled'

export type HomeworkFilter = 'open' | 'done' | HomeworkState | 'all'

export const studentPortalApi = {
  me: () => get<PortalMe>('/me/'),
  changePassword: (body: { current_password: string; new_password: string; new_password_confirm: string }) =>
    post<{ must_change_password: boolean }>('/password/', body),
  dashboard: (id: number) => get<PortalDashboard>(`${s(id)}/dashboard/`),
  schedule: (id: number, start: string, end: string) =>
    get<{ start: string; end: string; lessons: PortalLesson[] }>(`${s(id)}/schedule/`, { start, end }),
  homework: (id: number, state: HomeworkFilter, page = 1) =>
    get<Paginated<PortalHomework>>(`${s(id)}/homework/`, { state: state === 'all' ? undefined : state, page }),
  nextHomework: (id: number) => get<NextHomework>(`${s(id)}/homework/next/`),
  homeworkDetail: (id: number, homeworkId: number) => get<PortalHomeworkDetail>(`${s(id)}/homework/${homeworkId}/`),
  attendance: (id: number, year: number, month: number) => get<PortalAttendanceMonth>(`${s(id)}/attendance/`, { year, month }),
  notifications: (id: number) => get<{ results: PortalNotification[] }>(`${s(id)}/notifications/`),
  feedback: (id: number) => get<{ results: FeedbackItem[] }>(`${s(id)}/feedback/`),
  achievements: (id: number) => get<AchievementsOverview>(`${s(id)}/achievements/`),
  payments: (id: number) => get<PortalFinance>(`${s(id)}/payments/`),
  transactions: (id: number, status: TransactionFilter) =>
    get<{ results: PortalTransaction[] }>(`${s(id)}/payments/transactions/`, { status }),
  paymentDocuments: (id: number) => get<{ receipts: PortalReceipt[]; invoices: PortalInvoice[] }>(`${s(id)}/payments/documents/`),
  receipt: (id: number, receiptId: number) => get<PortalReceiptDetail>(`${s(id)}/payments/receipts/${receiptId}/`),
  /** The accounting system's own receipt PDF (read-only). */
  receiptPdf: (id: number, receiptId: number, download = false) =>
    apiClient
      .get<Blob>(`${BASE}${s(id)}/payments/receipts/${receiptId}/pdf/`, { params: download ? { download: 1 } : {}, responseType: 'blob' })
      .then((r) => r.data),
  monthlyReport: (id: number, year: number, month: number) => get<MonthlyReport>(`${s(id)}/reports/monthly/`, { year, month }),
  monthlyReportPdf: (id: number, year: number, month: number, lang: string) =>
    apiClient
      .get<Blob>(`${BASE}${s(id)}/reports/monthly/pdf/`, { params: { year, month, lang }, responseType: 'blob' })
      .then((r) => r.data),
}
