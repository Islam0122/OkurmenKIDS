import type { AcademicProgress } from '@/types/academicProgress'

/** Раздел «Академия» кабинета операционного директора (backend:
 * /api/v1/operations/academy/…, только чтение; цифры — из Reports / KPI,
 * «Прогресс студентов», оплаты обучения, рейтинга XP и стипендий). */
import type { FiltersEcho } from './operations'

type Rate = number | null
type Money = string | null
interface Ref { id: number; name: string }
interface Option { value: string; label: string }

export interface AcademyMeta {
  programs: Ref[]
  groups: Ref[]
  teachers: Ref[]
  subjects: Ref[]
  group_statuses: Option[]
  student_statuses: Option[]
  thresholds: Record<string, number>
  finance_visible: boolean
}

export interface Paged<T> {
  count: number
  page: number
  pages: number
  page_size: number
  results: T[]
}

export interface GroupPlan { completed: number; planned: number; remaining: number | null; progress: Rate }

export interface AcademyGroupRow {
  id: number
  name: string
  program: string
  program_id: number
  status: string
  status_display: string
  start_date: string | null
  trainers: { id: number; name: string; subject?: string | null }[]
  trainer_names: string
  students: { total: number; active: number; left: number; new: number; returned: number }
  lessons: { total: number; held: number; cancelled: number; due: number }
  attendance_rate: Rate
  homework_rate: Rate
  test_score_rate: Rate
  progress_rate: Rate
  kpi: Rate
  kpi_level: string
  has_data: boolean
  plan: GroupPlan
  /** Учебный месяц и прогресс по учебным месяцам программы (apps.academic_progress). */
  academic: AcademicProgress
}

export interface AcademyGroupsResponse extends Paged<AcademyGroupRow> {
  filters: FiltersEcho
  summary: { groups: number; active: number; students: number; average_attendance: Rate; attention: number }
}

export interface StudentProgressRow {
  id: number
  name: string
  status: string
  status_display: string
  in_group_now: boolean
  lessons_held: number
  attended: number
  absences: number
  attendance_rate: Rate
  homework_due: number
  homework_done: number
  homework_rate: Rate
  average_score: Rate
  test_average: Rate
  tests_count: number
  change: Record<string, Rate>
  xp?: number
  achievements?: number
}

export interface Achievement { kind: string; title: string; date: string; amount: Money; period: string; student?: string; student_id?: number }

export interface Assessments {
  tests: { attempts: number; passed: number; pass_rate: Rate; average_score: Rate }
  exams: { attempts: number; passed: number; pass_rate: Rate; average_score: Rate }
  sessions: { id: number; title: string; type: 'exam' | 'test'; attempts: number; passed: number; average_score: Rate }[]
}

export interface AcademyGroupDetail {
  group: { id: number; name: string; program: string; status: string; status_display: string; start_date: string | null; end_date: string | null; max_students: number | null }
  students: AcademyGroupRow['students']
  lessons: AcademyGroupRow['lessons']
  attendance: { total: number; present: number; late: number; absent: number; excused: number; rate: Rate }
  homework: { assigned: number; results: number; submitted: number; not_submitted: number; completion_rate: Rate; average_score: Rate }
  tests: { attempts: number; passed: number; average_score: Rate }
  trainers: { id: number; name: string; subject: string | null }[]
  plan: GroupPlan
  academic: AcademicProgress
  schedule: { day: string; start: string; end: string; subject: string | null; trainer: string | null; room: string | null; is_active: boolean }[]
  lesson_history: { id: number; date: string; number: number | null; start: string | null; topic: string; subject: string | null; trainer: string | null; status: string; status_display: string; attendance: { marked: number; attended: number } }[]
  student_progress: StudentProgressRow[]
  assessments: Assessments
  achievements: Achievement[]
  xp_total: number
  monthly: { month: string; attendance_rate: Rate; homework_rate: Rate; test_score_rate: Rate; kpi: Rate; students: number | null }[]
}

export interface StudentFinance { contracts: number; contract_amount: Money; paid: Money; debt: Money }

export interface AcademyStudentRow {
  id: number
  name: string
  status: string
  status_display: string
  group: Ref | null
  program: string | null
  trainers: string[]
  enrollment_date: string | null
  attendance_rate: Rate
  homework_rate: Rate
  average_score: Rate
  progress_rate: Rate
  level: string | null
  finance: StudentFinance | null
}

export interface AcademyStudentsResponse extends Paged<AcademyStudentRow> {
  filters: FiltersEcho
  finance_visible: boolean
}

export interface ContractCard {
  id: number
  plan: string
  program: string | null
  subject: string | null
  status: string
  status_display: string
  start_date: string
  discount_reason: string
  original: Money
  discount: Money
  final: Money
  paid: Money
  debt: Money
  due_now: Money
  overdue: Money
  paid_in_full: boolean
}

export interface StudentPaymentRow {
  id: number
  date: string
  amount: string
  kind: string
  kind_display: string
  method_display: string
  status: string
  status_display: string
  group: string | null
  program: string | null
  comment: string
}

export interface AcademyStudentProfile {
  filters: FiltersEcho
  student: {
    id: number; name: string; status: string; status_display: string; enrollment_date: string | null
    group: (Ref & { status_display: string }) | null; program: string | null
    trainers: { id: number; name: string; subject: string | null }[]
  }
  academic: {
    attendance_total: number; attended: number; attendance_rate: Rate; homework_results: number
    homework_submitted: number; homework_rate: Rate; average_score: Rate; progress_rate: Rate; level: string | null
    period: StudentProgressRow | null
    lessons: {
      id: number; date: string; lesson_number: number | null; topic: string; subject: string | null
      attendance: string | null; attendance_display: string | null
      homework: { id: number; title: string; status: string | null; status_display: string; score: number | null }[]
    }[]
    tests: { id: string; title: string; date: string | null; score: number; passed: boolean | null }[]
    assessments: Assessments
    xp: { attendance: number; homework: number; tests: number; total: number }
    achievements: Achievement[]
    badges_tracked: boolean
  }
  history: { date: string; type: string; type_display: string; group: string | null; from_group: string | null }[]
  finance: { contracts: ContractCard[]; payments: StudentPaymentRow[] } | null
}

export interface PerformanceRow {
  id: number
  name: string
  group: string
  group_id: number | null
  status_display: string
  attendance_total: number
  attended: number
  missed: number
  attendance_rate: Rate
  homework_rate: Rate
  average_score: Rate
  progress_rate: Rate
  level: string
  xp: number
  achievements: number
  change: { attendance_rate: Rate; homework_rate: Rate; average_score: Rate }
}

export interface AcademyPerformanceResponse extends Paged<PerformanceRow> {
  filters: FiltersEcho
  previous_period: { start: string; end: string }
  indicators: {
    attendance_rate: Rate; attended: number; missed: number; homework_rate: Rate; homework_average: Rate
    test_average: Rate; activity_rate: Rate; progress_rate: Rate; kpi: Rate; kpi_level: string | null
    exams: Assessments['exams']; tests: Assessments['tests']; xp: number; achievements: number
    /** Студентов, посетивших хотя бы одно занятие периода, из `students`. */
    active_students: number; students: number
  }
  previous: { attendance_rate: Rate; attended: number; missed: number; homework_rate: Rate; test_average: Rate; progress_rate: Rate; activity_rate: Rate; exams: Assessments['exams']; xp: number }
  change: Record<'attendance_rate' | 'homework_rate' | 'test_average' | 'progress_rate' | 'activity_rate', Rate>
  badges_tracked: boolean
}

export interface AttentionRow {
  id: number
  name: string
  group: string | null
  group_id: number | null
  status: string
  status_display: string
  attendance_rate: Rate
  homework_rate: Rate
  reasons: string[]
}

export interface AcademyMonthlyResponse {
  filters: FiltersEcho
  indicators: {
    active_students: number; new_students: number; left_students: number; returned_students: number
    transferred_students: number; attendance_rate: Rate; homework_rate: Rate; academic_performance: Rate
    test_average: Rate; kpi: Rate; achievements: number; xp: number; attention: number; groups: number
  }
  dynamics: { month: string; attendance_rate: Rate; homework_rate: Rate; test_average: Rate; progress_rate: Rate; kpi: Rate; active: number; new: number; left: number }[]
  groups: { id: number; name: string; program: string; students: number; attendance_rate: Rate; homework_rate: Rate; test_score_rate: Rate; kpi: Rate; kpi_level: string }[]
  attention: AttentionRow[]
  thresholds: Record<string, number>
  badges_tracked: boolean
}
