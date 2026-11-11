import type { LucideIcon } from 'lucide-react'
import { Award, BookOpen, CalendarDays, FolderKanban, Home, Info, Mail, MessageSquareQuote, Newspaper, Users } from 'lucide-react'

import type { MessageKey } from '@/i18n'

export interface NavItem {
  path: string
  label: MessageKey
  icon: LucideIcon
  /** Shown in the main header (the rest live in "More" and the footer). */
  primary?: boolean
}

/** The ten public sections — one list for the header, mobile menu, footer and sitemap. */
export const NAV: NavItem[] = [
  { path: '/', label: 'nav.home', icon: Home },
  { path: '/about', label: 'nav.about', icon: Info, primary: true },
  { path: '/courses', label: 'nav.courses', icon: BookOpen, primary: true },
  { path: '/projects', label: 'nav.projects', icon: FolderKanban, primary: true },
  { path: '/achievements', label: 'nav.achievements', icon: Award, primary: true },
  { path: '/news', label: 'nav.news', icon: Newspaper, primary: true },
  { path: '/events', label: 'nav.events', icon: CalendarDays, primary: true },
  { path: '/team', label: 'nav.team', icon: Users },
  { path: '/testimonials', label: 'nav.testimonials', icon: MessageSquareQuote },
  { path: '/contacts', label: 'nav.contacts', icon: Mail },
]

export const BRAND = {
  name: 'Okurmen Kids Digital',
  short: 'Okurmen Kids',
  tagline: 'Learn. Create. Achieve.',
} as const
