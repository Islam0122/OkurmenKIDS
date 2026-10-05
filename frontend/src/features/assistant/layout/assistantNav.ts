import {
  Award,
  CalendarDays,
  ClipboardCheck,
  GraduationCap,
  LayoutDashboard,
  MessageSquareText,
  User,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface AssistantNavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Exact match only (the dashboard is the parent of every route). */
  end?: boolean
}

/**
 * The Assistant Workspace sidebar — operations only. No KPI, analytics,
 * trainer control or reports: those are the Team Lead's (/app), never the
 * Assistant's. «Мероприятия» and «Уведомления» are not listed because the
 * academy has no event or notification module yet; they appear here once
 * the backend has one.
 */
export const ASSISTANT_NAV: AssistantNavItem[] = [
  { to: '/assistant', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/assistant/groups', label: 'Группы', icon: Users },
  { to: '/assistant/students', label: 'Студенты', icon: GraduationCap },
  { to: '/assistant/schedule', label: 'Расписание', icon: CalendarDays },
  { to: '/assistant/attendance', label: 'Посещаемость', icon: ClipboardCheck },
  { to: '/assistant/scholarships', label: 'Стипендии', icon: Award },
  { to: '/assistant/surveys', label: 'Опросы', icon: MessageSquareText },
]

export const ASSISTANT_PROFILE: AssistantNavItem = { to: '/assistant/profile', label: 'Профиль', icon: User }

/** The phone bottom bar: the four everyday sections; everything else is in the menu. */
export const ASSISTANT_MOBILE_PRIMARY = ASSISTANT_NAV.slice(0, 4)
