/** `apps.scholarships` API shapes. Decimal fields arrive as strings (DRF default). */

export type ScholarshipPeriodStatus = 'draft' | 'approved'

export type EligibilityStatus =
  | 'eligible'
  | 'not_full_period'
  | 'inactive'
  | 'no_data'
  | 'incomplete_data'
  | 'below_threshold'

export type AwardStatus = 'pending' | 'approved'

/** What a Teacher sees of a period (`TeacherPeriodSerializer`). */
export interface ScholarshipPeriodBrief {
  id: number
  award_day: number
  period_start: string
  period_end: string
  evaluation_date: string
  status: ScholarshipPeriodStatus
}

/** Admin view (`ScholarshipPeriodSerializer`). */
export interface ScholarshipPeriod extends ScholarshipPeriodBrief {
  max_recipients?: number
  attendance_weight?: string
  homework_weight?: string
  feedback_weight?: string
  evaluations_count?: number | null
  eligible_count?: number | null
  recipients_count?: number | null
  approved_at?: string | null
  last_calculated_at?: string | null
}

export interface ScholarshipEvaluation {
  id: number
  period: number
  student: number
  student_name: string
  group_name: string
  course_name: string
  enrollment_date: string | null
  overall_score: string | null
  attendance_score: string | null
  homework_score: string | null
  feedback_score: string | null
  lessons_count: number
  subjects_count: number
  rank: number | null
  eligibility_status: EligibilityStatus
  ineligibility_reason: string
  award_status: AwardStatus | null
}

export interface ScholarshipAnalytics {
  total_evaluated: number
  total_eligible: number
  total_recipients: number
  max_recipients: number
  incomplete_data: number
  averages: { overall: string | null; attendance: string | null; homework: string | null; feedback: string | null }
}

export interface TrainerFeedback {
  id: number
  period: number
  student: number
  student_name: string
  subject: number
  subject_name: string
  teacher: number
  teacher_name: string
  progress: number
  participation: number
  discipline: number
  understanding: number
  comment: string
  score: string
}

export interface TrainerFeedbackInput {
  progress: number
  participation: number
  discipline: number
  understanding: number
  comment: string
}

export interface RequiredFeedbackItem {
  student: number
  student_name: string
  subject: number
  subject_name: string
  is_submitted: boolean
  feedback: TrainerFeedback | null
}

export interface RequiredFeedbackResponse {
  period: ScholarshipPeriodBrief
  total: number
  missing: number
  items: RequiredFeedbackItem[]
}

export const ELIGIBILITY_LABELS: Record<EligibilityStatus, string> = {
  eligible: 'Допущен',
  not_full_period: 'Не весь период',
  inactive: 'Неактивен',
  no_data: 'Нет данных',
  incomplete_data: 'Неполные данные',
  below_threshold: 'Ниже порога',
}

export const FEEDBACK_CRITERIA: { key: keyof Omit<TrainerFeedbackInput, 'comment'>; label: string }[] = [
  { key: 'progress', label: 'Прогресс' },
  { key: 'participation', label: 'Активность на занятиях' },
  { key: 'discipline', label: 'Дисциплина' },
  { key: 'understanding', label: 'Понимание материала' },
]
