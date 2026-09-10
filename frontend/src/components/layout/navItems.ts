import {
  BarChart3,
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  GraduationCap,
  LayoutDashboard,
  NotebookPen,
  User,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { UserRole } from '@/types/auth'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Omitted = visible to every role. */
  roles?: UserRole[]
}

/**
 * Full sidebar order (desktop) — mirrors the "main logic" of the portal.
 *
 * A Trainer's day-to-day work is Group-first: "Мои группы" -> a Group ->
 * its schedule/students/attendance/homework, not a flat top-level browse of
 * every Student/Lesson/Attendance/Homework record in the system. So those
 * stay Admin-only entries here — a Teacher still reaches the same data
 * through a Group's own tabs (see GroupDetailPage), just not as a separate
 * main section.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/app/dashboard', label: 'Сегодня', icon: LayoutDashboard },
  { to: '/app/schedule', label: 'Расписание', icon: CalendarDays },
  { to: '/app/groups', label: 'Мои группы', icon: Users },
  { to: '/app/students', label: 'Студенты', icon: GraduationCap, roles: ['admin'] },
  { to: '/app/lessons', label: 'Занятия', icon: BookOpen, roles: ['admin'] },
  { to: '/app/attendance', label: 'Посещаемость', icon: ClipboardCheck, roles: ['admin'] },
  { to: '/app/homework', label: 'Домашние задания', icon: NotebookPen, roles: ['admin'] },
  { to: '/app/kpi', label: 'KPI', icon: BarChart3 },
]

export const PROFILE_NAV_ITEM: NavItem = { to: '/app/profile', label: 'Профиль', icon: User }

function visibleTo(role: UserRole | undefined, item: NavItem): boolean {
  return !item.roles || (role !== undefined && item.roles.includes(role))
}

export function getNavItems(role: UserRole | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => visibleTo(role, item))
}

function itemFor(to: string): NavItem {
  const item = NAV_ITEMS.find((candidate) => candidate.to === to)
  if (!item) throw new Error(`Unknown nav item: ${to}`)
  return item
}

/** The mobile bottom bar's primary tabs. Admin gets Главная/Расписание/Группы/Занятия/Профиль;
 * a Teacher gets KPI instead of the admin-only Занятия list, keeping 5 tabs. */
export function getMobilePrimaryNav(role: UserRole | undefined): NavItem[] {
  const dashboard = itemFor('/app/dashboard')
  const schedule = itemFor('/app/schedule')
  const groups = itemFor('/app/groups')
  const lessons = itemFor('/app/lessons')
  const kpi = itemFor('/app/kpi')

  return role === 'admin'
    ? [dashboard, schedule, groups, lessons, PROFILE_NAV_ITEM]
    : [dashboard, schedule, groups, kpi, PROFILE_NAV_ITEM]
}

/** Everything else, reached on mobile through the header's "Ещё" menu. */
export function getMobileMoreNav(role: UserRole | undefined): NavItem[] {
  const primary = new Set(getMobilePrimaryNav(role).map((item) => item.to))
  return getNavItems(role).filter((item) => !primary.has(item.to))
}
