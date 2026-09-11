import type {
  Group,
  GroupScheduleLesson,
  GroupScheduleSlot,
  GroupTeacherSummary,
  Lesson,
  Subject,
  Teacher,
} from '@/types/academy'
import type { AttendanceRecord } from '@/types/attendance'
import type { User } from '@/types/auth'
import type { Homework, HomeworkResult } from '@/types/homework'
import type { AnalyticsDashboard, ComparisonMetric } from '@/types/kpi'
import type { Paginated } from '@/types/common'

export function paginated<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results }
}

export function buildUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    username: 'trainer1',
    email: 'trainer1@example.com',
    first_name: 'Айгуль',
    last_name: 'Сатыбалдиева',
    role: 'teacher',
    is_verified: true,
    is_active: true,
    ...overrides,
  }
}

export function buildSubject(overrides: Partial<Subject> = {}): Subject {
  return {
    id: 1,
    name: 'Робототехника',
    description: '',
    is_active: true,
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-01-01T00:00:00Z',
    ...overrides,
  }
}

export function buildTeacher(overrides: Partial<Teacher> = {}): Teacher {
  return {
    id: 1,
    user: buildUser(),
    subjects: [buildSubject()],
    phone: '+996700000000',
    image: null,
    position: 'Тренер по робототехнике',
    experience_years: 3,
    bio: 'Веду занятия по робототехнике для детей 8-12 лет.',
    hire_date: '2023-01-10',
    is_active: true,
    created_at: '2023-01-10T00:00:00Z',
    updated_at: '2023-01-10T00:00:00Z',
    ...overrides,
  }
}

export function buildGroupScheduleSlot(overrides: Partial<GroupScheduleSlot> = {}): GroupScheduleSlot {
  return {
    id: 1,
    group: 1,
    teacher: 1,
    teacher_name: 'Айгуль Сатыбалдиева',
    subject: 1,
    subject_name: 'Робототехника',
    day_of_week: 'mon',
    day_of_week_label: 'Понедельник',
    start_time: '15:00:00',
    end_time: '16:30:00',
    room: 1,
    room_name: 'Кабинет 101',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function buildGroupTeacherSummary(overrides: Partial<GroupTeacherSummary> = {}): GroupTeacherSummary {
  return {
    id: 1,
    group: 1,
    teacher: 1,
    teacher_detail: buildTeacher(),
    subject: 1,
    subject_detail: buildSubject(),
    is_active: true,
    is_legacy_primary: false,
    schedules: [buildGroupScheduleSlot()],
    lesson_plans_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function buildGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: 1,
    name: 'Роботы-1',
    course: 1,
    course_name: 'Робототехника: базовый курс',
    start_date: '2026-01-10',
    end_date: null,
    schedules: [buildGroupScheduleSlot()],
    teachers: [buildGroupTeacherSummary()],
    students_count: 2,
    max_students: 12,
    status: 'active',
    status_display: 'Активна',
    description: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function buildLesson(overrides: Partial<Lesson> = {}): Lesson {
  return {
    id: 1,
    group: 1,
    group_name: 'Роботы-1',
    plan: null,
    lesson_number: 1,
    date: '2026-09-10',
    start_time: '15:00:00',
    end_time: '16:30:00',
    room: 1,
    room_name: 'Кабинет 101',
    subject: 1,
    subject_name: 'Робототехника',
    topic: 'Введение в конструктор',
    description: '',
    youtube_url: '',
    presentation_urls: [],
    status: 'planned',
    status_display: 'Запланировано',
    cancellation_reason: '',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

export function buildGroupScheduleLesson(overrides: Partial<GroupScheduleLesson> = {}): GroupScheduleLesson {
  return {
    ...buildLesson(),
    weekday: 'mon',
    weekday_label: 'Понедельник',
    ...overrides,
  }
}

export function buildAttendanceRecord(overrides: Partial<AttendanceRecord> = {}): AttendanceRecord {
  return {
    id: null,
    student: 1,
    student_name: 'Иванов Пётр',
    lesson: 1,
    group_name: 'Роботы-1',
    lesson_date: '2026-09-10',
    status: 'present',
    status_display: 'Присутствовал',
    comment: '',
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

export function buildHomework(overrides: Partial<Homework> = {}): Homework {
  return {
    id: 1,
    lesson: 1,
    group_name: 'Роботы-1',
    lesson_date: '2026-09-10',
    title: 'Собрать простого робота',
    description: 'Собрать робота по инструкции и сфотографировать результат.',
    deadline: '2026-09-15',
    results_count: 0,
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
    ...overrides,
  }
}

export function buildHomeworkResult(overrides: Partial<HomeworkResult> = {}): HomeworkResult {
  return {
    id: null,
    homework: 1,
    homework_title: 'Собрать простого робота',
    student: 1,
    student_name: 'Иванов Пётр',
    status: 'not_submitted',
    status_display: 'Не сдано',
    score: null,
    comment: '',
    submitted_at: null,
    checked_at: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

/** A `ComparisonMetric` with no comparison period requested — the common
 * case in tests that don't care about trend/previous_value. */
export function buildMetric(value: number, overrides: Partial<ComparisonMetric> = {}): ComparisonMetric {
  return { value, previous_value: null, change: null, change_percent: null, trend: 'stable', ...overrides }
}

export function buildAnalyticsDashboard(overrides: Partial<AnalyticsDashboard> = {}): AnalyticsDashboard {
  return {
    period: { key: 'this_month', start_date: '2026-09-01', end_date: '2026-09-10' },
    comparison: null,
    filters: { teacher_id: null, group_id: null, course_id: null, subject_id: null },
    health: {
      score: 87,
      level: 'good',
      components: { attendance: 91, homework: 87, lesson_completion: 94, retention: 92, teacher_workload: 81 },
    },
    students: {
      total_students: buildMetric(20),
      active_students: buildMetric(18),
      inactive_students: buildMetric(2),
      new_students: buildMetric(3),
      students_left: buildMetric(1),
      average_students_per_group: buildMetric(10),
      groups_with_free_capacity: buildMetric(1),
      groups_at_capacity: buildMetric(1),
    },
    teachers: {
      total_teachers: buildMetric(1),
      active_teachers: buildMetric(1),
      teachers_with_lessons: buildMetric(1),
      teachers_without_lessons: buildMetric(0),
      average_lessons_per_teacher: buildMetric(10),
      teacher_workload: [],
    },
    groups: {
      total_groups: buildMetric(2),
      active_groups: buildMetric(2),
      paused_groups: buildMetric(0),
      completed_groups: buildMetric(0),
      cancelled_groups: buildMetric(0),
      average_students_per_group: buildMetric(10),
      groups_near_capacity: buildMetric(0),
    },
    lessons: {
      lessons_today: buildMetric(1),
      lessons_scheduled: buildMetric(10),
      lessons_completed: buildMetric(8),
      lessons_cancelled: buildMetric(1),
      lesson_completion_rate: buildMetric(80),
      lessons_by_teacher: [],
      lessons_by_subject: [],
    },
    attendance: {
      attendance_rate: buildMetric(92.5),
      present_count: buildMetric(30),
      absent_count: buildMetric(5),
      late_count: buildMetric(5),
      excused_count: buildMetric(0),
      students_with_repeated_absences: buildMetric(0),
      attendance_trend: [],
    },
    homework: {
      homework_count: buildMetric(10),
      submitted_count: buildMetric(10),
      not_submitted_count: buildMetric(3),
      checked_count: buildMetric(3),
      late_count: buildMetric(0),
      submission_rate: buildMetric(80),
      average_score: buildMetric(8.4),
      homework_completion_trend: [],
    },
    insights: [],
    ...overrides,
  }
}
