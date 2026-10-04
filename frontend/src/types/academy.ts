import type { User } from '@/types/auth'
import type { DayOfWeek } from '@/types/common'

/** `apps.users.serializers.SubjectSerializer` */
export interface Subject {
  id: number
  name: string
  description: string
  is_active: boolean
  created_at: string
  updated_at: string
}

/** `apps.users.serializers.TeacherSerializer` — fully read-only for a Teacher. */
export interface Teacher {
  id: number
  user: User
  subjects: Subject[]
  phone: string
  image: string | null
  position: string
  experience_years: number
  bio: string
  hire_date: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.CourseSerializer` */
export interface Course {
  id: number
  name: string
  count_lesson: number
  subjects: number[]
  subjects_detail: Subject[]
  lesson_plans_count: number
  description: string
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.CourseLessonPlanSerializer` */
export interface CourseLessonPlan {
  id: number
  course: number
  course_name: string
  lesson_number: number
  subject: number
  subject_name: string
  topic: string
  description: string
  youtube_url: string
  presentation_urls: string[]
  homework_title: string
  homework_description: string
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.RoomSerializer` */
export interface Room {
  id: number
  name: string
  capacity: number | null
  description: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type GroupStatus = 'active' | 'paused' | 'completed' | 'cancelled'

/** `apps.academy.serializers.GroupScheduleSlotSerializer` — one recurring
 * weekly slot of a Teaching Program (see `GroupTeacherSummary`). */
export interface GroupScheduleSlot {
  id: number
  group: number
  teacher: number
  teacher_name: string
  subject: number | null
  subject_name: string | null
  day_of_week: DayOfWeek
  day_of_week_label: string
  start_time: string
  end_time: string
  room: number | null
  room_name: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.GroupTeacherSerializer` — one independent
 * Teaching Program within a Group: one teacher teaching one subject on its
 * own schedule. A Group can have several of these, each fully equal — none
 * is a "main" teacher/schedule. */
export interface GroupTeacherSummary {
  id: number
  group: number
  teacher: number
  teacher_detail: Teacher
  subject: number | null
  subject_detail: Subject | null
  is_active: boolean
  is_legacy_primary: boolean
  schedules: GroupScheduleSlot[]
  lesson_plans_count: number
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.GroupSerializer` (read shape — `students` is
 * write-only on the API). `teacher`/`room`/`start_time`/`end_time`/
 * `days_of_week` are legacy fields on the backend model, kept only for
 * historical data — never exposed here; `teachers` (this Group's Teaching
 * Programs) and `schedules` (every one of their slots, flattened) are the
 * real source of truth for who teaches what, when, and where. */
export interface Group {
  id: number
  name: string
  course: number
  course_name: string
  start_date: string
  end_date: string | null
  schedules: GroupScheduleSlot[]
  teachers: GroupTeacherSummary[]
  students_count: number
  max_students: number | null
  status: GroupStatus
  status_display: string
  description: string
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.StudentSerializer` */
export interface Student {
  id: number
  first_name: string
  last_name: string
  full_name: string
  phone: string
  parent_phone: string
  group: number | null
  group_name: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type LessonStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled'

export interface LessonCompletionRequirement {
  key: string
  label: string
  satisfied: boolean
}

export interface LessonCompletionProgress {
  satisfied: number
  total: number
  is_complete: boolean
}

/** `apps.academy.services.lesson_summary.attendance_summary` — real,
 * backend-calculated counts, never re-derived from a separate roster fetch. */
export interface LessonAttendanceSummary {
  total_students: number
  present: number
  absent: number
  late: number
  excused: number
  /** `null` until at least one student has been marked. */
  attendance_rate: number | null
}

/** `apps.academy.services.lesson_summary.homework_summary` — `null` when
 * the lesson has no Homework at all. */
export interface LessonHomeworkSummary {
  results_total: number
  checked: number
  pending: number
  /** `null` until at least one result has a score. */
  average_score: number | null
}

/** `apps.academy.serializers.LessonSerializer` */
export interface Lesson {
  id: number
  group: number
  group_name: string
  plan: number | null
  lesson_number: number
  date: string
  start_time: string
  end_time: string
  room: number | null
  room_name: string | null
  subject: number | null
  subject_name: string | null
  teacher_name: string | null
  topic: string
  description: string
  youtube_url: string
  presentation_urls: string[]
  status: LessonStatus
  status_display: string
  cancellation_reason: string
  homework_not_required: boolean
  started_at: string | null
  completed_at: string | null
  completed_by: number | null
  completed_by_name: string | null
  can_start: boolean
  can_complete: boolean
  can_cancel: boolean
  attendance_completed: boolean
  homework_added: boolean
  completion_requirements: LessonCompletionRequirement[]
  completion_progress: LessonCompletionProgress
  attendance_summary: LessonAttendanceSummary
  homework_summary: LessonHomeworkSummary | null
  attendance_editable: boolean
  created_at: string
  updated_at: string
}

/** `apps.academy.serializers.GroupScheduleLessonSerializer` — a Lesson plus
 * which weekday it fell on (from the backend's canonical mon/tue/... map,
 * never a locale-formatted date). */
export interface GroupScheduleLesson extends Lesson {
  weekday: DayOfWeek
  weekday_label: string
}

/** `apps.academy.serializers.GroupScheduleSerializer` — response of
 * `GET /api/v1/groups/{id}/schedule/`: the group itself (with its Teaching
 * Programs' own recurring schedule slots) plus every dated Lesson it has. */
export interface GroupSchedule {
  group: Group
  lessons: GroupScheduleLesson[]
}

/** `apps.academy.serializers.RoomOccupancySerializer` — one Lesson occupying
 * a room within the requested window. */
export interface RoomOccupancy {
  room: number
  room_name: string
  lesson: number
  group: number | null
  group_name: string | null
  start_time: string
  end_time: string
}

/** `apps.academy.serializers.RoomAvailabilitySerializer` — response of
 * `GET /academy/rooms/available/?date=&start_time=&end_time=`. */
export interface RoomAvailability {
  date: string
  start_time: string
  end_time: string
  available: Room[]
  occupied: RoomOccupancy[]
}

/** GET /lessons/{id}/parent-report/ — «Мини-отчёт родителям», built on the backend
 * (services.parent_report). `messages` holds the ready Kyrgyz text in both built-in
 * wordings (`message` = `messages.system`); `warnings` are Russian notes for the
 * trainer only (never part of the message). */
export interface ParentLessonReport {
  lesson_id: number
  group: string
  lesson_date: string
  topic: string | null
  present_students: string[]
  absent_students: string[]
  /** The previous lesson's homework, whose results are reported today; null when there was none. */
  homework_checked: { title: string; lesson_id: number; lesson_number: number; lesson_date: string } | null
  homework_not_completed: string[]
  homework_partial: string[]
  next_homework: string | null
  warnings: string[]
  message: string
  messages: Record<ParentReportStyle, string>
}

/** «Автор отчёта»: «🤖 Система» and «👨‍🏫 Тренер» texts come from the backend;
 * «✏️ Свой вариант» is the trainer's own edit, kept only in the dialog. */
export type ParentReportStyle = 'system' | 'trainer'
export type ParentReportType = ParentReportStyle | 'custom'

/** `GET /groups/{id}/academic-config/` — «Учебная конфигурация» (Admin /
 * Team Lead): the group's programs (trainer + subject), each with its own
 * weekly slots — every day its own time and room. */
export interface AcademicSlot {
  id: number
  day: DayOfWeek
  day_label: string
  start: string
  end: string
  room: { id: number; name: string } | null
  is_active: boolean
}

export interface AcademicProgram {
  id: number
  subject: { id: number; name: string } | null
  teacher: { id: number; name: string }
  is_active: boolean
  /** A program with lessons can't change its subject (backend rule). */
  has_lessons: boolean
  assigned_by: string | null
  assigned_at: string | null
  slots: AcademicSlot[]
}

export interface AcademicConfig {
  group: { id: number; name: string; course: string; status: string }
  programs: AcademicProgram[]
  subjects: { id: number; name: string }[]
  trainers: { id: number; name: string; subjects: string[] }[]
  rooms: { id: number; name: string; capacity: number | null }[]
  weekdays: { code: DayOfWeek; label: string }[]
  saved_program?: number
}

export interface AcademicSlotInput {
  id?: number
  day: DayOfWeek
  start: string
  end: string
  room: number | null
}

export interface AcademicProgramInput {
  teacher: number
  subject: number
  schedule: AcademicSlotInput[]
}

/** `POST /groups/{id}/generate-lessons/` (the existing generator). */
export interface GenerateLessonsResult {
  created_count: number
  updated_count: number
  already_existed: number
  expected_total: number
  first_date: string | null
  last_date: string | null
  warnings: string[]
  errors: string[]
}
