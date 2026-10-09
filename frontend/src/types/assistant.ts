/** Shapes of the Assistant Workspace API (`/api/v1/assistant/`, backend: apps.assistant). */
import type { DayOfWeek } from '@/types/common'

export interface Ref {
  id: number
  name: string
}

export type GroupStatus = 'active' | 'paused' | 'completed' | 'cancelled'
export type StudentStatus = 'active' | 'paused' | 'completed' | 'withdrawn'
export type LessonStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled'
export type AttendanceStatus = 'present' | 'absent' | 'late' | 'excused'

export interface AttentionItem {
  key: string
  count: number
  label: string
  to: string
  tone: 'warning' | 'danger' | 'info'
}

export interface AssistantLesson {
  id: number
  date: string
  start: string
  end: string
  group: Ref
  subject: Ref | null
  teacher: Ref | null
  room: Ref | null
  topic: string
  lesson_number: number
  status: LessonStatus
  status_display: string
  students_count: number | null
  schedule_overridden: boolean
}

export interface ActivityRow {
  id: string
  kind: 'group' | 'student' | 'schedule' | 'lesson' | 'status'
  title: string
  detail: string
  at: string
  by: string
  link: string | null
}

export interface Dashboard {
  date: string
  cards: {
    active_groups: number
    groups_new_this_month: number
    students_total: number
    active_students: number
    todays_lessons: number
    todays_completed: number
    new_students: number
  }
  today: AssistantLesson[]
  attention: AttentionItem[]
  activity: ActivityRow[]
}

export interface SearchResults {
  students: { id: number; name: string; group: string | null; status: StudentStatus; status_display: string }[]
  groups: { id: number; name: string; course: string; status: GroupStatus; status_display: string }[]
  teachers: Ref[]
  lessons: AssistantLesson[]
}

export interface GroupCardData {
  id: number
  name: string
  course: Ref
  status: GroupStatus
  status_display: string
  students_count: number
  max_students: number | null
  teachers: string[]
  schedule: string
  start_date: string
  end_date: string | null
}

export interface Slot {
  id: number
  day: DayOfWeek
  day_label: string
  start: string
  end: string
  room: Ref | null
}

export interface Program {
  id: number
  teacher: Ref
  subject: Ref | null
  is_active: boolean
  slots: Slot[]
}

export interface StudentRow {
  id: number
  first_name: string
  last_name: string
  full_name: string
  phone: string
  parent_phone: string
  group: Ref | null
  course: Ref | null
  status: StudentStatus
  status_display: string
  enrollment_date: string | null
  attendance_percent: number | null
}

export interface HistoryRow {
  id: string
  kind: string
  title: string
  reason?: string
  comment?: string
  date: string
  created_at: string
  performed_by: string
}

export interface GroupDetail extends GroupCardData {
  description: string
  created_at: string
  programs: Program[]
  students: StudentRow[]
  upcoming_lessons: AssistantLesson[]
  recent_lessons: AssistantLesson[]
  lessons_total: number
  today_lesson: AssistantLesson | null
  next_lesson: AssistantLesson | null
  recent_attendance: (AssistantLesson & { attended: number; marked: number })[]
  attendance: { attended: number; marked: number; percent: number | null }
  exams: { id: string; title: string; status: string; status_display: string; created_at: string }[]
  surveys: { id: number; title: string; status: string; status_display: string; created_at: string }[]
  history: HistoryRow[]
  generation?: GenerationSummary
}

export interface GenerationSummary {
  created: number
  updated: number
  rescheduled: number
  expected: number
  missing: number
  warnings: string[]
  errors: string[]
}

export interface StudentDetail extends StudentRow {
  created_at: string
  teachers: string[]
  group_status: string | null
  schedule: (Slot & { teacher: Ref; subject: Ref | null })[]
  attendance: {
    attended: number
    marked: number
    records: { id: number; date: string; group: string; subject: string; status: AttendanceStatus; status_display: string; comment: string }[]
  }
  homework: { id: number; title: string; date: string; subject: string; status: string; status_display: string; score: number | null }[]
  exams: { id: string; title: string; subject: string; score: number; finished_at: string }[]
  scholarships: {
    id: number
    period: string
    period_start: string
    period_end: string
    award_date: string
    rank: number
    amount: string
    status: string
    status_display: string
    payment_status: string
    payment_status_display: string
  }[]
  surveys: { id: number; title: string; status: string; status_display: string; public_token: string | null }[]
  history: HistoryRow[]
}

export interface Options {
  courses: { id: number; name: string; count_lesson: number; subjects: Ref[] }[]
  teachers: { id: number; name: string; subjects: number[] }[]
  rooms: { id: number; name: string; capacity: number | null }[]
  groups: { id: number; name: string; course: string; status: GroupStatus; students_count: number; max_students: number | null }[]
  weekdays: { code: DayOfWeek; label: string; short: string }[]
  deactivation_reasons: { value: string; label: string }[]
  group_statuses: { value: GroupStatus; label: string }[]
}

export interface ScheduleConflict {
  kind: 'teacher' | 'group' | 'room'
  kind_label: string
  name: string
  day: DayOfWeek
  day_label: string
  slots: { group: Ref; teacher: Ref; start: string; end: string }[]
}

export interface ScheduleData {
  start: string
  end: string
  lessons: AssistantLesson[]
  conflicts: ScheduleConflict[]
}

export interface AttendanceLesson extends AssistantLesson {
  present: number
  absent: number
  unmarked: number
  records: { student: Ref; status: AttendanceStatus | null; comment: string }[]
}

export interface ScholarshipAwardRow {
  id: number
  student: Ref
  group: string
  rank: number
  score: string | null
  amount: string
  status: string
  status_display: string
  payment_status: string
  payment_status_display: string
}

export interface ScholarshipPeriodRow {
  id: number
  title: string
  period_start: string
  period_end: string
  evaluation_date: string
  status: 'draft' | 'approved'
  status_display: string
  max_recipients: number | null
  award_amount: string | null
  awards: ScholarshipAwardRow[]
}

export interface ScholarshipCandidate {
  id: number
  student_id: number
  student_name: string
  group_name: string
  rank: number | null
  overall_score: string | null
}

export interface BulkResult {
  done: number
  failed: number
  results: { id: number; name: string; ok: boolean; error?: string }[]
}

export interface SlotInput {
  id?: number | null
  day: DayOfWeek
  start: string
  end: string
  room?: number | null
}

export interface ProgramInput {
  program?: number | null
  teacher: number
  subject: number
  slots: SlotInput[]
}

export interface GroupCreateInput {
  name: string
  course: number
  start_date: string
  end_date?: string | null
  max_students?: number | null
  description?: string
  programs: ProgramInput[]
  students: number[]
  generate_lessons: boolean
}

export type BulkAction = 'transfer' | 'add_to_group' | 'deactivate' | 'activate'

// Surveys — the existing feedback API (`/api/v1/feedback/surveys/`).
export type SurveyStatus = 'draft' | 'published' | 'closed'
export type QuestionType = 'text' | 'single_choice' | 'multiple_choice'

export interface Survey {
  id: number
  title: string
  description: string
  audience: 'parent' | 'student'
  visibility_mode: 'open' | 'anonymous' | 'both'
  status: SurveyStatus
  availability: string
  group: number | null
  public_url: string | null
  question_count: number
  response_count: number
  published_at: string | null
  created_at: string
}

export interface SurveyQuestion {
  id: number
  text: string
  question_type: QuestionType
  is_required: boolean
  order: number
  options: { id: number; text: string; order: number }[]
}

export interface SurveyDetail extends Survey {
  questions: SurveyQuestion[]
}

export interface SurveyAnalytics {
  response_count: number
  questions: {
    id: number
    index: number
    text: string
    question_type: QuestionType
    answered: number
    options?: { id: number; text: string; count: number; pct: number }[]
    texts?: { text: string; submitted_at: string }[]
  }[]
}

// Read-only records (attendance / homework of a group) and «Контроль».
export interface LessonHead {
  id: number
  date: string
  start: string
  end: string
  lesson_number: number
  topic: string
  subject: Ref | null
  teacher: Ref | null
  status: LessonStatus
  status_display: string
  group: Ref
}

export interface AttendanceLessonRow extends LessonHead {
  present: number
  absent: number
  late: number
  excused: number
  attended: number
  marked: number
  unmarked: number
  percent: number | null
  student_status: AttendanceStatus | null
}

export interface GroupAttendance {
  summary: { present: number; absent: number; late: number; excused: number; marked: number; unmarked: number; attended: number; percent: number | null; lessons: number }
  lessons: AttendanceLessonRow[]
  students: { id: number; name: string; attended: number; absent: number; late: number; marked: number; percent: number | null; consecutive_absences: number }[]
}

export type HomeworkState = 'open' | 'review' | 'complete' | 'missing'

export interface HomeworkRow {
  id: number
  title: string
  lesson: { id: number; number: number; topic: string; date: string }
  teacher?: Ref | null
  deadline: string | null
  issued: string
  done: number
  pending: number
  checked: number
  expected: number
  not_done: number
  percent: number | null
  due: boolean
  status: HomeworkState
  status_display: string
}

export interface GroupHomework {
  summary: { total: number; complete: number; missing: number; review: number; open: number; average_percent: number | null }
  homeworks: HomeworkRow[]
}

export interface HomeworkDetail extends HomeworkRow {
  description: string
  lesson: HomeworkRow['lesson'] & LessonHead
  teacher: Ref | null
  students: {
    student: Ref
    state: 'done' | 'review' | 'not_done' | 'waiting'
    status_display: string
    submitted_at: string | null
    checked_at: string | null
    score: number | null
    comment: string
  }[]
}

export interface LessonDetail extends LessonHead {
  description: string
  cancellation_reason: string
  attendance: { attended: number; marked: number; total: number; percent: number | null }
  records: { student: Ref; status: AttendanceStatus | null; status_display: string; comment: string }[]
  homeworks: HomeworkRow[]
}

export type ControlStatus = 'normal' | 'attention' | 'low' | 'risk' | 'no_data'
export type ControlCategory = 'not_attending' | 'no_homework' | 'both' | 'frequent_absence' | 'stale_homework' | 'low_activity' | 'risk'
export type ControlPeriod = '7d' | '14d' | '30d' | 'month' | 'all'

export interface StudentActivity {
  student_id: number
  name: string
  group: Ref | null
  attendance: number | null
  attended: number
  absent: number
  late: number
  excused: number
  marked: number
  lessons: number
  consecutive_absences: number
  homework: number | null
  homework_done: number
  homework_due: number
  homework_missed: number
  homework_pending: number
  consecutive_missed_homework: number
  last_attended: string | null
  last_lesson: string | null
  last_teacher: string
  last_homework_done: string | null
  last_homework_done_title: string
  last_homework_given: string | null
  last_activity: string | null
  status: ControlStatus
  status_label: string
  categories: ControlCategory[]
}

export interface ControlOverview {
  period: ControlPeriod
  thresholds: Record<string, number>
  kpis: Record<ControlCategory, number>
  categories: { key: ControlCategory; label: string; count: number }[]
  students: StudentActivity[]
  total: number
}

export interface ControlProfile {
  student: { id: number; name: string; status?: StudentStatus; status_display?: string }
  period?: ControlPeriod
  activity: StudentActivity | null
  timeline: { date: string; kind: 'attendance' | 'homework'; ok: boolean; neutral: boolean; text: string; detail: string }[]
  note: string
}

/** «Месячный отчёт» — one month of students and groups (no trainers). */
export interface ReportStudent {
  /** Why the student is listed: «Низкая посещаемость», «Не выполняет ДЗ», «Нет активности»… */
  reason: string
  student_id: number
  name: string
  group: Ref | null
  attendance: number | null
  attended: number
  marked: number
  absent: number
  consecutive_absences: number
  homework: number | null
  homework_done: number
  homework_due: number
  homework_missed: number
  consecutive_missed_homework: number
  last_activity: string | null
  status: ControlStatus
  status_label: string
}

export interface MonthlyReport {
  year: number
  month: number
  title: string
  start: string
  end: string
  until: string
  is_complete: boolean
  generated_at: string
  overview: {
    groups_total: number
    groups_active: number
    groups_inactive: number
    students_total: number
    students_active: number
    students_new: number
    students_deactivated: number
    attendance_percent: number | null
    homework_percent: number | null
    students_at_risk: number
  }
  attendance: {
    lessons: number
    marked: number
    attended: number
    absent: number
    excused: number
    percent: number | null
    groups: { group: Ref; students: number; lessons: number; attended: number; absent: number; marked: number; percent: number | null }[]
  }
  homework: {
    given: number
    due: number
    done: number
    not_done: number
    pending: number
    expected: number
    percent: number | null
    groups: { group: Ref; homeworks: number; due: number; done: number; not_done: number; pending: number; expected: number; percent: number | null }[]
  }
  students: {
    attendance_attention: ReportStudent[]
    homework_attention: ReportStudent[]
    risk: ReportStudent[]
    no_activity: ReportStudent[]
    activity: {
      analysed: number
      normal: number
      attention: number
      low: number
      risk: number
      no_data: number
      not_attending: number
      no_homework: number
      no_activity: number
    }
  }
  surveys: {
    surveys: number
    participants: number
    participation: number | null
    average: number | null
    low_ratings: number
    texts_total: number
    rows: {
      id: number
      title: string
      group: Ref | null
      audience_display: string
      status_display: string
      participants: number
      expected: number | null
      participation: number | null
      average: number | null
      ratings: number
      low_ratings: number
    }[]
    quotes: { text: string; count: number; survey: string; question: string; date: string }[]
  }
  scholarships: {
    awards: number
    recipients: number
    total_amount: number
    paid: number
    paid_amount: number
    groups: string[]
    rows: {
      id: number
      student: Ref
      group: string
      title: string
      amount: number
      reason: string
      status: string
      status_display: string
      payment_status: string
      payment_display: string
      award_date: string
    }[]
  }
  conclusions: {
    good: string[]
    attention: string[]
    groups: string[]
    students: { student_id: number; name: string; group: string; reason: string }[]
  }
}
