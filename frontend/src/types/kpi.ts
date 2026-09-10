/**
 * All six KPI models are read-only computed snapshots for a Teacher —
 * `apps.academy.services.kpi_calculator` derives every number from
 * Lesson/Attendance/Homework/HomeworkResult; only Admin can trigger a
 * recalculation. Field names mirror the DRF serializers exactly.
 */

export interface KPIGroup {
  id: number
  group: number
  group_name: string
  date_from: string
  date_to: string
  total_students: number
  total_lessons: number
  completed_lessons: number
  cancelled_lessons: number
  attendance_percent: number
  homework_completion_percent: number
  average_score: number
  created_at: string
  updated_at: string
}

export interface KPITeacher {
  id: number
  teacher: number
  teacher_name: string
  date_from: string
  date_to: string
  total_groups: number
  total_lessons: number
  completed_lessons: number
  cancelled_lessons: number
  attendance_percent: number
  homework_completion_percent: number
  average_student_score: number
  created_at: string
  updated_at: string
}

export interface KPIStudent {
  id: number
  student: number
  student_name: string
  group: number
  group_name: string
  date_from: string
  date_to: string
  total_lessons: number
  present_count: number
  absent_count: number
  late_count: number
  attendance_percent: number
  total_homeworks: number
  completed_homeworks: number
  missed_homeworks: number
  homework_completion_percent: number
  average_score: number
  created_at: string
  updated_at: string
}

export interface KPILesson {
  id: number
  lesson: number
  group_name: string
  lesson_date: string
  total_students: number
  present_count: number
  absent_count: number
  late_count: number
  attendance_percent: number
  total_homeworks: number
  homework_completed_count: number
  homework_completion_percent: number
  average_homework_score: number
  created_at: string
  updated_at: string
}

export interface KPIAttendance {
  id: number
  group: number
  group_name: string
  date_from: string
  date_to: string
  total_records: number
  present_count: number
  absent_count: number
  late_count: number
  excused_count: number
  attendance_percent: number
  created_at: string
  updated_at: string
}

export interface KPIHomework {
  id: number
  group: number
  group_name: string
  date_from: string
  date_to: string
  total_homeworks: number
  total_results: number
  submitted_count: number
  checked_count: number
  not_submitted_count: number
  late_count: number
  completion_percent: number
  average_score: number
  created_at: string
  updated_at: string
}
