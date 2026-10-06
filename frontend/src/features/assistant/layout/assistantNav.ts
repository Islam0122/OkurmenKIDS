import {
  Award,
  CalendarDays,
  ClipboardCheck,
  FileBarChart,
  GraduationCap,
  LayoutDashboard,
  MessageSquareText,
  ShieldAlert,
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

export interface AssistantNavSection {
  title: string | null
  items: AssistantNavItem[]
}

/**
 * The Assistant Workspace sidebar — operations only. No KPI, analytics,
 * trainer control or trainer reports: those are the Team Lead's (/app),
 * never the Assistant's; «Отчёты» is the monthly report on students and
 * groups only. «Мероприятия» and «Уведомления» are not listed because the
 * academy has no event or notification module yet; they appear here once
 * the backend has one.
 */
export const ASSISTANT_SECTIONS: AssistantNavSection[] = [
  { title: null, items: [{ to: '/assistant', label: 'Dashboard', icon: LayoutDashboard, end: true }] },
  {
    title: 'Академия',
    items: [
      { to: '/assistant/groups', label: 'Группы', icon: Users },
      { to: '/assistant/students', label: 'Студенты', icon: GraduationCap },
      { to: '/assistant/schedule', label: 'Расписание', icon: CalendarDays },
    ],
  },
  {
    title: 'Операции',
    items: [
      { to: '/assistant/control', label: 'Контроль', icon: ShieldAlert },
      { to: '/assistant/attendance', label: 'Посещаемость', icon: ClipboardCheck },
      { to: '/assistant/scholarships', label: 'Стипендии', icon: Award },
      { to: '/assistant/surveys', label: 'Опросы', icon: MessageSquareText },
    ],
  },
  {
    title: 'Отчёты',
    items: [{ to: '/assistant/reports', label: 'Месячный отчёт', icon: FileBarChart }],
  },
]

export const ASSISTANT_NAV: AssistantNavItem[] = ASSISTANT_SECTIONS.flatMap((section) => section.items)

export const ASSISTANT_PROFILE: AssistantNavItem = { to: '/assistant/profile', label: 'Профиль', icon: User }

/** The phone bottom bar: the four everyday sections; everything else is in the menu. */
export const ASSISTANT_MOBILE_PRIMARY = ASSISTANT_NAV.slice(0, 4)
