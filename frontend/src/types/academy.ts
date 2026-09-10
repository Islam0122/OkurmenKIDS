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

/** `apps.academy.serializers.GroupSerializer` (read shape — `students` is write-only on the API). */
export interface Group {
  id: number
  name: string
  course: number
  course_name: string
  teacher: number
  teacher_name: string
  room: number | null
  room_name: string | null
  start_date: string
  end_date: string | null
  start_time: string
  end_time: string
  days_of_week: DayOfWeek[]
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
