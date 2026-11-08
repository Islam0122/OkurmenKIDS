import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
  Briefcase,
  FolderKanban,
  Globe,
  MessageSquareHeart,
  BookOpenCheck,
  CalendarClock,
  Code2,
  Compass,
  GraduationCap,
  Languages,
  Megaphone,
  Sparkles,
  Trophy,
  Users,
} from 'lucide-react'

import { homeFor } from '@/lib/roles'
import type { User, UserRole } from '@/types/auth'

import type { ProgramId } from './i18n'

/**
 * OKURMENKIDS DIGITAL — the single source of truth for every application the
 * portal launches. Change a destination here (or through the matching
 * `VITE_PORTAL_*_URL` variable at build time) and the launcher follows.
 *
 * Destinations are either an internal React Router path of THIS build
 * (`/schedule`, `/leaderboard`, `/app/...`) or an absolute `https://` URL of
 * a separately deployed app. Nothing here is a guess: internal paths are
 * routes registered in `app/router`, external URLs are the deployments the
 * academy already runs.
 */

export const PORTAL_PATH = '/portal'
export const PROGRAMS_PATH = '/portal/programs'

export type PortalAppId =
  | 'lms'
  | 'training'
  | 'schedule'
  | 'leaderboard'
  | 'news'
  | 'performance'
  | 'programs'

export interface PortalApp {
  id: PortalAppId
  /** Name, tagline and feature chips come from `i18n.tsx` (`apps[id]`). */
  icon: LucideIcon
  /** Internal path or absolute URL. `null` = destination not configured yet. */
  href: string | null
  /** Sign-in needed before the app can be used (guests see a lock and go to /login). */
  requiresAuth?: boolean
  /** When signed in, only these roles see the card (UI only — the backend enforces access). */
  roles?: UserRole[]
  /** Visually emphasised, wider card. */
  featured?: boolean
}

/** Absolute http(s) URL → opened in a new tab; anything else is an app route. */
export function isExternal(href: string): boolean {
  return /^https?:\/\//i.test(href)
}

/** Env override → default. An empty variable keeps the default. */
function env(value: string | undefined, fallback: string | null): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : fallback
}

const ENV = import.meta.env

/** Roles that work inside the LMS cabinet (/app). Others are redirected to their own cabinet by AppLayout. */
const LMS_ROLES: UserRole[] = ['admin', 'teacher', 'team_lead']

export const PORTAL_APPS: PortalApp[] = [
  {
    id: 'lms',
    icon: GraduationCap,
    href: env(ENV.VITE_PORTAL_LMS_URL, '/app/dashboard'),
    requiresAuth: true,
  },
  {
    id: 'training',
    icon: BookOpenCheck,
    href: env(ENV.VITE_PORTAL_TRAINING_URL, 'https://training-portal-theta.vercel.app/'),
  },
  {
    id: 'schedule',
    icon: CalendarClock,
    href: env(ENV.VITE_PORTAL_SCHEDULE_URL, '/schedule'),
  },
  {
    id: 'leaderboard',
    icon: Trophy,
    href: env(ENV.VITE_PORTAL_LEADERBOARD_URL, '/leaderboard'),
  },
  {
    id: 'news',
    icon: Megaphone,
    href: env(ENV.VITE_PORTAL_NEWS_URL, '/app/news'),
    requiresAuth: true,
    roles: LMS_ROLES,
  },
  {
    id: 'performance',
    icon: BarChart3,
    href: env(ENV.VITE_PORTAL_PERFORMANCE_URL, 'https://okurmen-kids-drab.vercel.app/monthly-performance'),
  },
  {
    id: 'programs',
    icon: Compass,
    href: env(ENV.VITE_PORTAL_PROGRAMS_URL, PROGRAMS_PATH),
    featured: true,
  },
]

export type PortalServiceId = 'projects' | 'feedback' | 'website' | 'careers'

/** «More from Okurmen» — the compact row under the main grid. Texts: `i18n.tsx` (`services[id]`). */
export interface PortalService {
  id: PortalServiceId
  icon: LucideIcon
  /** Internal path or absolute URL; `null` = not configured yet (the card shows «Soon»). */
  href: string | null
  /** A signed-in role that works elsewhere opens its own page instead of `href`. */
  roleHrefs?: Partial<Record<UserRole, string>>
  requiresAuth?: boolean
  /** When signed in, only these roles see the card (UI only — the backend enforces access). */
  roles?: UserRole[]
  /** Open an internal route in a new tab too (a separate public site of this build). */
  newTab?: boolean
}

export const PORTAL_SERVICES: PortalService[] = [
  {
    // Проекты студентов (features/projects): тренер, Team Lead и администратор — /trainer/projects,
    // операционный директор и директор — опубликованные проекты в своём кабинете.
    id: 'projects',
    icon: FolderKanban,
    href: env(ENV.VITE_PORTAL_PROJECTS_URL, '/trainer/projects'),
    roleHrefs: { operations_director: '/operations/academy/projects', director: '/operations/academy/projects' },
    requiresAuth: true,
    roles: ['teacher', 'team_lead', 'admin', 'operations_director', 'director'],
  },
  {
    // Опросы обратной связи (apps.feedback) отвечают по личной ссылке на каждый опрос — общего
    // публичного адреса нет. Ассистент и администратор ведут опросы в /assistant/surveys;
    // VITE_PORTAL_FEEDBACK_URL задаёт общую форму, когда она появится.
    id: 'feedback',
    icon: MessageSquareHeart,
    href: env(ENV.VITE_PORTAL_FEEDBACK_URL, null),
    roleHrefs: { assistant: '/assistant/surveys', admin: '/assistant/surveys' },
  },
  {
    // Официальный сайт академии: адрес в проекте не настроен — задайте VITE_PORTAL_WEBSITE_URL.
    id: 'website',
    icon: Globe,
    href: env(ENV.VITE_PORTAL_WEBSITE_URL, null),
  },
  {
    // Карьерный сайт этой же сборки (features/careers) или его отдельный домен.
    id: 'careers',
    icon: Briefcase,
    href: env(ENV.VITE_PORTAL_CAREERS_URL, '/careers'),
    newTab: true,
  },
]

/** Where a «More from Okurmen» card leads for this visitor. */
export function resolveService(service: PortalService, user: User | null): CardState {
  const href = (user && service.roleHrefs?.[user.role]) || service.href
  if (!href) return { kind: 'unavailable' }
  if (isExternal(href)) return { kind: 'open', href, external: true }
  if (service.requiresAuth && !user) return { kind: 'login', href }
  return { kind: 'open', href, external: Boolean(service.newTab) }
}

export type CardState =
  /** Opens the destination. */
  | { kind: 'open'; href: string; external: boolean }
  /** Guest on a protected app: goes to the login page, then back to the app. */
  | { kind: 'login'; href: string }
  /** No destination configured. */
  | { kind: 'unavailable' }

/** Whether a card is shown at all for this visitor. */
export function isVisible(app: { roles?: UserRole[] }, user: User | null): boolean {
  if (!user || !app.roles) return true
  return app.roles.includes(user.role)
}

/** Where a click on the card leads for this visitor. */
export function resolveCard(app: PortalApp, user: User | null): CardState {
  if (!app.href) return { kind: 'unavailable' }
  if (isExternal(app.href)) return { kind: 'open', href: app.href, external: true }
  if (app.requiresAuth && !user) return { kind: 'login', href: app.href }
  // A signed-in employee lands in the cabinet of their own role (accounting, HR, …).
  const href = app.id === 'lms' && user ? homeFor(user.role, app.href) : app.href
  return { kind: 'open', href, external: false }
}

export interface Program {
  id: ProgramId
  icon: LucideIcon
}

/** Program directions shown on the Our Programs card and page; their texts live in `i18n.tsx` (`programs[id]`). */
export const PROGRAMS: Program[] = [
  { id: 'it', icon: Code2 },
  { id: 'english', icon: Languages },
  { id: 'soft-skills', icon: Users },
  { id: 'other', icon: Sparkles },
]
