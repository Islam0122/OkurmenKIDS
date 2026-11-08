import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
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

/**
 * OKURMEN DIGITAL — the single source of truth for every application the
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
  name: string
  /** One line under the name. */
  tagline: string
  /** Short feature chips. */
  features: string[]
  icon: LucideIcon
  /** Internal path or absolute URL. `null` = destination not configured yet. */
  href: string | null
  /** Sign-in needed before the app can be used (guests see a lock and go to /login). */
  requiresAuth?: boolean
  /** When signed in, only these roles see the card (UI only — the backend enforces access). */
  roles?: UserRole[]
  /** Visually emphasised, wider card. */
  featured?: boolean
  /** Longer copy for the featured card. */
  description?: string
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
    name: 'LMS',
    tagline: 'Learning Management System',
    features: ['Groups', 'Lessons', 'Homework', 'Attendance', 'Students'],
    icon: GraduationCap,
    href: env(ENV.VITE_PORTAL_LMS_URL, '/app/dashboard'),
    requiresAuth: true,
  },
  {
    id: 'training',
    name: 'Training & Exams',
    tagline: 'Practice, tests and exams',
    features: ['Practice', 'Tests', 'Exams', 'Exercises'],
    icon: BookOpenCheck,
    href: env(ENV.VITE_PORTAL_TRAINING_URL, 'https://training-portal-theta.vercel.app/'),
  },
  {
    id: 'schedule',
    name: 'Schedule',
    tagline: 'Lessons and group timetables',
    features: ['Lessons', 'Groups', 'Trainers'],
    icon: CalendarClock,
    href: env(ENV.VITE_PORTAL_SCHEDULE_URL, '/schedule'),
  },
  {
    id: 'leaderboard',
    name: 'Leaderboard',
    tagline: 'Rankings, XP and achievements',
    features: ['Rankings', 'XP', 'Competitions'],
    icon: Trophy,
    href: env(ENV.VITE_PORTAL_LEADERBOARD_URL, '/leaderboard'),
  },
  {
    id: 'programs',
    name: 'Our Programs',
    tagline: 'IT · English · Soft Skills',
    description: 'Explore our educational programs and discover your learning path.',
    features: ['IT', 'English', 'Soft Skills', 'Learning paths'],
    icon: Compass,
    href: env(ENV.VITE_PORTAL_PROGRAMS_URL, PROGRAMS_PATH),
    featured: true,
  },
  {
    id: 'news',
    name: 'News',
    tagline: 'Announcements and events',
    features: ['Announcements', 'Events', 'Updates'],
    icon: Megaphone,
    href: env(ENV.VITE_PORTAL_NEWS_URL, '/app/news'),
    requiresAuth: true,
    roles: LMS_ROLES,
  },
  {
    id: 'performance',
    name: 'Monthly Performance',
    tagline: 'Attendance and progress by month',
    features: ['Attendance', 'Homework', 'Progress'],
    icon: BarChart3,
    href: env(ENV.VITE_PORTAL_PERFORMANCE_URL, 'https://okurmen-kids-drab.vercel.app/monthly-performance'),
  },
]

export type CardState =
  /** Opens the destination. */
  | { kind: 'open'; href: string; external: boolean }
  /** Guest on a protected app: goes to the login page, then back to the app. */
  | { kind: 'login'; href: string }
  /** No destination configured. */
  | { kind: 'unavailable' }

/** Whether a card is shown at all for this visitor. */
export function isVisible(app: PortalApp, user: User | null): boolean {
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
  id: string
  name: string
  summary: string
  topics: string[]
  icon: LucideIcon
}

/** Program directions shown on /portal/programs. Edit here — no other file needs to change. */
export const PROGRAMS: Program[] = [
  {
    id: 'it',
    name: 'IT',
    summary: 'Programming and digital skills — from the first lines of code to real projects.',
    topics: ['Programming', 'Computer literacy', 'Student projects'],
    icon: Code2,
  },
  {
    id: 'english',
    name: 'English',
    summary: 'Spoken and written English for every level, built around practice.',
    topics: ['Speaking', 'Grammar', 'Vocabulary'],
    icon: Languages,
  },
  {
    id: 'soft-skills',
    name: 'Soft Skills',
    summary: 'Communication, teamwork and confidence that help in school and beyond.',
    topics: ['Communication', 'Teamwork', 'Public speaking'],
    icon: Users,
  },
  {
    id: 'other',
    name: 'Other programs',
    summary: 'Additional academy courses, intensives and seasonal programs.',
    topics: ['Intensives', 'Seasonal courses', 'Events'],
    icon: Sparkles,
  },
]
