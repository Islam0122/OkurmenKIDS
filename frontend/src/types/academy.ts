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

export type LessonStatus = 'planned' | 'completed' | 'cancelled'

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
  topic: string
  description: string
  youtube_url: string
  presentation_urls: string[]
  status: LessonStatus
  status_display: string
  cancellation_reason: string
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
