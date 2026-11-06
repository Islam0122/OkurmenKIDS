/** Monthly Academic Progress — /api/v1/academic-progress/ (backend: apps.academic_progress). */

export interface Ref {
  id: number
  name: string
}

export type ProgressStatus = 'needs_setup' | 'not_started' | 'in_progress' | 'completed'

export interface StudyMonth {
  number: number
  subject: Ref | null
  planned: number
  done: number
  remaining: number
  progress: number | null
  state: 'done' | 'current' | 'upcoming'
  first_date: string | null
  last_date: string | null
}

export interface AcademicProgress {
  configured: boolean
  status: ProgressStatus
  status_display: string
  reason: string
  lessons_in_lms: number
  lessons_before_lms: number
  history_confirmed: boolean
  last_lesson_date: string | null
  month: (StudyMonth & { label: string; next_lesson: number | null }) | null
  months: StudyMonth[]
  course: { done: number; planned: number; remaining: number; progress: number | null; extra: number } | null
  count_mode?: 'main' | 'all'
}

export interface StudentMonthProgress {
  id: number
  name: string
  month_attended: number
  month_held: number
  month_rate: number | null
  course_attended: number
  course_held: number
}

export interface GroupAcademicProgress {
  group: { id: number; name: string; course: Ref; start_date: string | null }
  progress: AcademicProgress
  students: StudentMonthProgress[]
  can_edit: boolean
}

export interface ProgramRow {
  id: number
  name: string
  configured: boolean
  lessons_per_month: number | null
  duration_months: number | null
  main_subject: Ref | null
  extra_subjects: Ref[]
  total_lessons: number | null
  groups: number
  groups_need_setup: number
  can_edit: boolean
}

export interface CurriculumSettings {
  lessons_per_month: number
  duration_months: number
  main_subject: Ref | null
  extra_subjects: Ref[]
  count_mode: 'main' | 'all'
  months: { number: number; subject: Ref | null; planned_lessons: number | null }[]
  blocks: { number: number; subject: Ref | null; planned: number }[]
  total_lessons: number
  updated_at: string
  updated_by: string | null
}

export interface ProgramDetail {
  course: { id: number; name: string; count_lesson: number; subjects: Ref[] }
  configured: boolean
  can_edit: boolean
  settings: CurriculumSettings | null
}

export interface ProgramInput {
  lessons_per_month: number
  duration_months: number
  main_subject: number | null
  extra_subjects: number[]
  count_mode: 'main' | 'all'
  months: { number: number; subject: number | null; planned_lessons: number | null }[]
}

export interface ProgressMeta {
  subjects: Ref[]
  can_edit: boolean
  presets: number[]
}
