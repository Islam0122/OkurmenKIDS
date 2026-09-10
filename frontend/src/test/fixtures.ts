import type { Group, Lesson, Subject, Teacher } from '@/types/academy'
import type { AttendanceRecord } from '@/types/attendance'
import type { User } from '@/types/auth'
import type { Homework, HomeworkResult } from '@/types/homework'
import type { KPITeacher } from '@/types/kpi'
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

export function buildGroup(overrides: Partial<Group> = {}): Group {
  return {
    id: 1,
    name: 'Роботы-1',
    course: 1,
    course_name: 'Робототехника: базовый курс',
    teacher: 1,
    teacher_name: 'Айгуль Сатыбалдиева',
    room: 1,
    room_name: 'Кабинет 101',
    start_date: '2026-01-10',
    end_date: null,
    start_time: '15:00:00',
    end_time: '16:30:00',
    days_of_week: ['mon', 'wed'],
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

export function buildKPITeacher(overrides: Partial<KPITeacher> = {}): KPITeacher {
  return {
    id: 1,
    teacher: 1,
    teacher_name: 'Айгуль Сатыбалдиева',
    date_from: '2026-09-01',
    date_to: '2026-09-10',
    total_groups: 2,
    total_lessons: 10,
    completed_lessons: 8,
    cancelled_lessons: 1,
    attendance_percent: 92.5,
    homework_completion_percent: 80,
    average_student_score: 8.4,
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
    ...overrides,
  }
}
