import {
  BarChart3,
  CalendarDays,
  CalendarRange,
  ClipboardCheck,
  FileBarChart,
  Gauge,
  GraduationCap,
  House,
  IdCard,
  Calendar,
  ListChecks,
  MonitorCheck,
  NotebookPen,
  School,
  ScrollText,
  Settings,
  ShieldCheck,
  TrendingUp,
  Users,
  Archive,
  CircleCheck,
  BookOpen,
  FileQuestion,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/**
 * Team Lead sidebar: sections that open on click, each link a real route of
 * the LMS (no placeholders). Icons come from the project's icon library
 * (lucide-react); the comment next to each names the Bootstrap Icon it
 * stands for, as the design spec lists them.
 *
 * Not here on purpose: «Уведомления» — the LMS has no notifications page for
 * a Team Lead (News is the Trainer feed, closed on the backend too).
 */
export interface TeamLeadLink {
  label: string
  to: string
  icon: LucideIcon
}

export interface TeamLeadSection {
  key: string
  label: string
  icon: LucideIcon
  /** A section without children is a plain link. */
  to?: string
  children?: TeamLeadLink[]
}

export const TEAM_LEAD_SECTIONS: TeamLeadSection[] = [
  { key: 'home', label: 'Главная', icon: House /* house */, to: '/app/dashboard' },
  // The day-to-day board: lessons, trainers' colors, rooms, conflicts (read only).
  { key: 'schedule', label: 'Расписание', icon: CalendarDays /* calendar-week */, to: '/app/schedule' },
  {
    key: 'analytics', label: 'Аналитика', icon: TrendingUp /* graph-up */,
    children: [
      { label: 'Общая аналитика', to: '/app/analytics', icon: BarChart3 /* bar-chart */ },
      { label: 'По группам', to: '/app/analytics?tab=groups', icon: Users /* people */ },
      { label: 'По тренерам', to: '/app/analytics?tab=teachers', icon: IdCard /* person-badge */ },
      { label: 'По студентам', to: '/app/analytics?tab=students', icon: GraduationCap /* mortarboard */ },
      { label: 'По предметам', to: '/app/analytics?tab=subjects', icon: BookOpen /* book */ },
    ],
  },
  {
    key: 'groups', label: 'Группы', icon: Users /* people */,
    children: [
      { label: 'Все группы', to: '/app/groups', icon: Users /* people */ },
      { label: 'Активные группы', to: '/app/groups?status=active', icon: CircleCheck /* check-circle */ },
      { label: 'Архив', to: '/app/groups?status=completed', icon: Archive /* archive */ },
      { label: 'Занятия', to: '/app/lessons', icon: Calendar /* calendar3 */ },
    ],
  },
  {
    key: 'trainers', label: 'Тренеры', icon: IdCard /* person-badge */,
    children: [
      { label: 'Все тренеры', to: '/app/trainers', icon: IdCard /* person-badge */ },
      { label: 'Контроль', to: '/app/control', icon: ShieldCheck /* shield-check */ },
    ],
  },
  {
    key: 'students', label: 'Студенты', icon: GraduationCap /* mortarboard */,
    children: [
      { label: 'Все студенты', to: '/app/students', icon: GraduationCap /* mortarboard */ },
      { label: 'Посещаемость', to: '/app/attendance', icon: ClipboardCheck /* clipboard-check */ },
      { label: 'Домашние задания', to: '/app/homework', icon: NotebookPen /* journal-text */ },
    ],
  },
  {
    key: 'tests', label: 'Тесты', icon: ClipboardCheck /* clipboard-check */,
    children: [
      { label: 'Все тесты', to: '/app/tests', icon: FileQuestion /* clipboard */ },
      { label: 'Тестовые сессии', to: '/app/exams', icon: ListChecks /* list-check */ },
      { label: 'Мониторинг', to: '/app/monitoring', icon: MonitorCheck /* display */ },
      { label: 'Результаты тестов', to: '/app/analytics?tab=tests', icon: BarChart3 /* bar-chart */ },
    ],
  },
  {
    key: 'kpi', label: 'KPI', icon: Gauge /* speedometer2 */,
    children: [
      { label: 'KPI академии', to: '/app/kpi', icon: Gauge /* speedometer2 */ },
      { label: 'KPI отчёты', to: '/app/academy-report', icon: School /* building */ },
    ],
  },
  {
    key: 'reports', label: 'Отчёты', icon: FileBarChart /* file-earmark-bar-graph */,
    children: [
      { label: 'Ежедневные', to: '/app/worklog?tab=reports&kind=daily', icon: CalendarDays /* calendar3 */ },
      { label: 'Еженедельные', to: '/app/worklog?tab=reports&kind=weekly', icon: CalendarRange /* calendar-week */ },
      { label: 'Ежемесячные', to: '/app/worklog?tab=reports&kind=monthly', icon: Calendar /* calendar-month */ },
      { label: 'Рабочий журнал', to: '/app/worklog', icon: ScrollText /* journal */ },
    ],
  },
]

export const TEAM_LEAD_SETTINGS: TeamLeadLink = { label: 'Настройки', to: '/app/profile', icon: Settings /* gear */ }

/** Every link of the Team Lead navigation, in order. */
export function teamLeadLinks(): TeamLeadLink[] {
  return [
    ...TEAM_LEAD_SECTIONS.flatMap((section) =>
      section.children ?? (section.to ? [{ label: section.label, to: section.to, icon: section.icon }] : []),
    ),
    TEAM_LEAD_SETTINGS,
  ]
}

function split(to: string): { path: string; query: URLSearchParams } {
  const [path, search = ''] = to.split('?')
  return { path, query: new URLSearchParams(search) }
}

/**
 * The one link that is active for the current location. A link matches when
 * its path is the current path (or a parent of it, e.g. a group's page under
 * «Все группы») and every query parameter it sets has the same value; the
 * link setting the most matching parameters wins, then the more specific
 * path, then the first in order. So `/app/analytics?tab=groups` lights up
 * «По группам», plain `/app/analytics` — «Общая аналитика».
 */
export function activeLink(pathname: string, search: string, links: TeamLeadLink[] = teamLeadLinks()): string | null {
  const current = new URLSearchParams(search)
  let best: { to: string; score: number } | null = null
  for (const link of links) {
    const { path, query } = split(link.to)
    const pathMatch = pathname === path ? 2 : pathname.startsWith(`${path}/`) ? 1 : 0
    if (!pathMatch) continue
    let matching = 0
    let ok = true
    query.forEach((value, key) => {
      if (current.get(key) === value) matching += 1
      else ok = false
    })
    if (!ok) continue
    const score = matching * 10 + pathMatch
    if (best === null || score > best.score) best = { to: link.to, score }
  }
  return best?.to ?? null
}

export function sectionOf(to: string | null): string | null {
  if (!to) return null
  return TEAM_LEAD_SECTIONS.find((section) => section.to === to || section.children?.some((child) => child.to === to))?.key ?? null
}
