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
