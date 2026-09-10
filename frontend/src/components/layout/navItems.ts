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

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

/** Full sidebar order (desktop) — mirrors the "main logic" of the portal from the spec. */
export const NAV_ITEMS: NavItem[] = [
  { to: '/app/dashboard', label: 'Сегодня', icon: LayoutDashboard },
  { to: '/app/schedule', label: 'Расписание', icon: CalendarDays },
  { to: '/app/groups', label: 'Группы', icon: Users },
  { to: '/app/students', label: 'Студенты', icon: GraduationCap },
  { to: '/app/lessons', label: 'Занятия', icon: BookOpen },
  { to: '/app/attendance', label: 'Посещаемость', icon: ClipboardCheck },
  { to: '/app/homework', label: 'Домашние задания', icon: NotebookPen },
  { to: '/app/kpi', label: 'KPI', icon: BarChart3 },
]

export const PROFILE_NAV_ITEM: NavItem = { to: '/app/profile', label: 'Профиль', icon: User }

/** The 5 tabs of the mobile bottom bar, exactly as specified: Главная/Расписание/Группы/Занятия/Профиль. */
export const MOBILE_PRIMARY_NAV: NavItem[] = [
  NAV_ITEMS[0],
  NAV_ITEMS[1],
  NAV_ITEMS[2],
  NAV_ITEMS[4],
  PROFILE_NAV_ITEM,
]

/** Everything else, reached on mobile through the header's "Ещё" menu. */
export const MOBILE_MORE_NAV: NavItem[] = [NAV_ITEMS[3], NAV_ITEMS[5], NAV_ITEMS[6], NAV_ITEMS[7]]
