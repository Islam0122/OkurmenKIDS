import {
  Award,
  BarChart3,
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  FileQuestion,
  FileText,
  GraduationCap,
  LineChart,
  LayoutDashboard,
  ListChecks,
  Megaphone,
  MonitorCheck,
  NotebookPen,
  School,
  ScrollText,
  ShieldCheck,
  User,
  UserCog,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { UserRole } from '@/types/auth'

export interface NavItem {
  to: string
  label: string
  /** One-word label for the phone bottom bar, where five tabs share 320px. */
  shortLabel?: string
  icon: LucideIcon
  /** Omitted = visible to every role. */
  roles?: UserRole[]
  /** A different label for some roles (e.g. a Team Lead's «Сессии»). */
  roleLabels?: Partial<Record<UserRole, string>>
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
 *
 * Team Lead (руководитель тренеров) reads the whole academy, so they get the
 * academy-wide browse entries (Тренеры, Студенты, Сессии, Посещаемость, ДЗ,
 * Аналитика, Отчёты) and never the Trainer-only ones (Мои отчёты, Стипендии,
 * Новости) nor anything of user/role/system management — those don't exist
 * in this portal at all (Django admin only, closed to a Team Lead on the
 * backend too).
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/app/dashboard', label: 'Сегодня', icon: LayoutDashboard, roleLabels: { team_lead: 'Dashboard' } },
  { to: '/app/schedule', label: 'Расписание', icon: CalendarDays, roles: ['admin', 'teacher', 'team_lead'] },
  { to: '/app/trainers', label: 'Тренеры', icon: UserCog, roles: ['admin', 'team_lead'] },
  { to: '/app/groups', label: 'Мои группы', shortLabel: 'Группы', icon: Users, roleLabels: { team_lead: 'Группы' } },
  { to: '/app/students', label: 'Студенты', icon: GraduationCap, roles: ['admin', 'team_lead'] },
  { to: '/app/lessons', label: 'Занятия', icon: BookOpen, roles: ['admin', 'team_lead'] },
  { to: '/app/attendance', label: 'Посещаемость', icon: ClipboardCheck, roles: ['admin', 'team_lead'] },
  { to: '/app/homework', label: 'Домашние задания', icon: NotebookPen, roles: ['admin', 'team_lead'], roleLabels: { team_lead: 'ДЗ' } },
  // Test sessions: a Trainer's own groups, monitored live (backend-scoped);
  // Admin / Team Lead — every session, plus create / start / take one.
  { to: '/app/exams', label: 'Экзамены', icon: ListChecks, roleLabels: { team_lead: 'Сессии' } },
  // Live attempts, violations and analytics of exams and trainers (backend-scoped).
  { to: '/app/monitoring', label: 'Мониторинг', icon: MonitorCheck },
  // The test bank, view only.
  { to: '/app/tests', label: 'Тесты', icon: FileQuestion, roles: ['team_lead'] },
  { to: '/app/kpi', label: 'KPI', icon: BarChart3 },
  // Посещаемость / ДЗ / баллы по каждому тренеру и группе.
  { to: '/app/control', label: 'Контроль', icon: ShieldCheck },
  { to: '/app/analytics', label: 'Аналитика', icon: LineChart, roles: ['admin', 'team_lead'] },
  { to: '/app/reports', label: 'Мои отчёты', icon: FileText, roles: ['teacher'] },
  // The Team Lead's own journal, tasks and reports (Admin reads them).
  { to: '/app/worklog', label: 'Рабочий журнал', shortLabel: 'Журнал', icon: ScrollText, roles: ['admin', 'team_lead'] },
  { to: '/app/academy-report', label: 'Отчёты академии', icon: School, roles: ['admin', 'team_lead'], roleLabels: { team_lead: 'Отчёты' } },
  { to: '/app/scholarships', label: 'Стипендии', icon: Award, roles: ['admin', 'teacher'] },
  { to: '/app/news', label: 'Новости', icon: Megaphone, roles: ['admin', 'teacher'] },
]

export const PROFILE_NAV_ITEM: NavItem = { to: '/app/profile', label: 'Профиль', icon: User }

function visibleTo(role: UserRole | undefined, item: NavItem): boolean {
  return !item.roles || (role !== undefined && item.roles.includes(role))
}

function labelled(role: UserRole | undefined, item: NavItem): NavItem {
  const label = role ? item.roleLabels?.[role] : undefined
  return label ? { ...item, label, shortLabel: item.shortLabel && label.length > 10 ? item.shortLabel : label } : item
}

export function getNavItems(role: UserRole | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => visibleTo(role, item)).map((item) => labelled(role, item))
}

/** Whether `role` has a nav entry for `path` (or a page under it). */
export function canOpen(role: UserRole | undefined, path: string): boolean {
  return getNavItems(role).some((item) => path === item.to || path.startsWith(`${item.to}/`))
}

function itemFor(to: string, role?: UserRole): NavItem {
  const item = NAV_ITEMS.find((candidate) => candidate.to === to)
  if (!item) throw new Error(`Unknown nav item: ${to}`)
  return labelled(role, item)
}

/** The mobile bottom bar's primary tabs. Admin gets Сегодня/Расписание/Группы/Занятия/Профиль;
 * a Teacher gets KPI instead of the admin-only Занятия list, keeping 5 tabs. */
export function getMobilePrimaryNav(role: UserRole | undefined): NavItem[] {
  if (role === 'team_lead') {
    return [
      itemFor('/app/dashboard', role),
      itemFor('/app/trainers', role),
      itemFor('/app/groups', role),
      itemFor('/app/analytics', role),
      PROFILE_NAV_ITEM,
    ]
  }
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
