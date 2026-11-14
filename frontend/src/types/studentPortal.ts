/** Student & Parent Portal API (backend: apps.portal, /api/v1/portal/). */

export interface Ref {
  id: number
  name: string
}

export interface PortalStudent {
  id: number
  first_name: string
  last_name: string
  full_name: string
  photo: string | null
  birth_date: string | null
  status: string
  group: Ref | null
  course: Ref | null
  branch: { id: number; name: string; name_ky: string; address: string; phone: string } | null
  enrollment_date: string | null
}

export interface PortalMe {
  login: string
  must_change_password: boolean
  can_view_payments: boolean
  students: PortalStudent[]
}

export type LessonStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled'
export type AttendanceMark = 'present' | 'absent' | 'late' | 'excused'

export interface PortalLesson {
  id: number
  date: string
  start: string | null
  end: string | null
  subject: Ref | null
  teacher: Ref | null
  group: Ref | null
  course: Ref | null
  room: Ref | null
  branch: Ref | null
  topic: string
  lesson_number: number | null
  status: LessonStatus
  cancellation_reason: string
  attendance: AttendanceMark | null
}

/** The trainer's own status from the offline grading form, or `awaiting` until one is saved. */
export type HomeworkState = 'awaiting' | 'not_submitted' | 'submitted' | 'late' | 'checked'

export interface PortalHomework {
  id: number
  title: string
  /** The date of the lesson the homework was given on. */
  assigned_date: string
  deadline: string | null
  days_left: number | null
  state: HomeworkState
  is_open: boolean
  lesson: { id: number; date: string; topic: string; lesson_number: number | null }
  subject: Ref | null
  teacher: Ref | null
  /** Only a grade the trainer entered; null before evaluation. */
  score: number | null
  has_feedback: boolean
  evaluated_at: string | null
  checked_at: string | null
  created_at: string
}

/** Read-only: homework is done outside the LMS and checked offline by the trainer. */
export interface PortalHomeworkDetail extends Omit<PortalHomework, 'lesson'> {
  description: string
  lesson: PortalHomework['lesson'] & { description: string }
  attachments: { kind: 'video' | 'presentation'; url: string }[]
  feedback: string
}

/** `/homework/next/`: the next scheduled lesson of each program with its homework (possibly none). */
export interface NextHomework {
  has_group: boolean
  lessons: { lesson: PortalLesson; homework: PortalHomeworkDetail[] }[]
}

export interface AttendanceSummary {
  marked: number
  present: number
  late: number
  absent: number
  excused: number
  attended: number
  percent: number | null
}

export interface XpParts {
  attendance: number
  homework: number
  tests: number
  total: number
}

export interface Achievement {
  code: 'scholarship' | 'perfect_attendance' | 'top_homework' | 'homework_streak' | 'level'
  date: string | null
  params: Record<string, number>
}

export interface FeedbackItem {
  kind: 'homework' | 'lesson' | 'evaluation'
  date: string | null
  text: string
  score: number | null
  title: string
  subject: Ref | null
  teacher: Ref | null
  criteria?: { progress: number; participation: number; discipline: number; understanding: number }
}

export type NotificationKind =
  | 'homework_not_submitted' | 'homework_due' | 'homework_new' | 'homework_checked' | 'lesson_cancelled' | 'payment_due'

export interface PortalNotification {
  id: string
  kind: NotificationKind
  date: string | null
  priority: number
  params: { homework_id?: number; lesson_id?: number; title?: string; days_left?: number; score?: number | null;
    subject?: string; start?: string | null; amount?: string }
}

export interface FinanceSummary {
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

export interface PortalDashboard {
  student: PortalStudent
  today: string
  today_lessons: PortalLesson[]
  upcoming_lessons: PortalLesson[]
  homework: { open: PortalHomework[]; open_count: number; not_submitted_count: number; next_deadline: string | null }
  attendance: { month: AttendanceSummary; overall: AttendanceSummary }
  performance: { average_score: number | null; month_average_score: number | null; homework_rate: number | null; scored_count: number }
  xp: { month: XpParts; total: number; level: { level: number; floor: number; next: number; progress: number } }
  achievements: Achievement[]
  feedback: FeedbackItem[]
  notifications: PortalNotification[]
  payments: FinanceSummary | null
}

export interface PortalAttendanceMonth {
  year: number
  month: number
  summary: AttendanceSummary
  records: { id: number; status: AttendanceMark; comment: string; excuse_reason: string; lesson: PortalLesson }[]
}

export interface MonthlyReport {
  student: PortalStudent
  period: { year: number; month: number; start: string; end: string; is_complete: boolean }
  attendance: { percent: number | null; total_lessons: number; marked: number; attended: number; missed: number; late: number; excused: number }
  homework: { assigned: number; completed: number; completion_rate: number | null; average_score: number | null; scored_count: number }
  tests: { count: number; average: number | null; items: { id: string; title: string; date: string | null; score: number; passed: boolean | null }[] }
  progress: {
    subjects: { subject: string; lessons: number; attendance_rate: number | null; homework_rate: number | null; average_score: number | null }[]
    change: { attendance_rate: number | null; homework_rate: number | null; average_score: number | null }
  }
  xp: XpParts
  comments: FeedbackItem[]
  trend: { year: number; month: number; attendance_rate: number | null; homework_rate: number | null; average_score: number | null; xp: number }[]
  lessons: { id: number; date: string; topic: string; subject: string | null; attendance: AttendanceMark | null; group: string;
    homework: { id: number; title: string; status: string | null; score: number | null }[] }[]
}

export interface PortalPayments {
  summary: FinanceSummary | null
  currency: string
  open_invoices: { id: number; number: string | null; kind: string; status: string; amount: string; balance: string; overdue_since: string | null; subject: string | null }[]
  history: { id: number; kind: 'payment' | 'refund'; amount: string; date: string; method: string; service_start: string | null; service_end: string | null }[]
}
