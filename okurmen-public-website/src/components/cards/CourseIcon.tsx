import { Bot, Code2, Gamepad2, Globe, Laptop, Palette, Terminal, type LucideIcon } from 'lucide-react'

import type { CourseIcon as IconName } from '@/types/api'

export const COURSE_ICONS: Record<IconName, LucideIcon> = {
  code: Code2,
  python: Terminal,
  web: Globe,
  game: Gamepad2,
  robot: Bot,
  digital: Laptop,
  design: Palette,
}

/** Accent per direction — subtle tints of the two brand colours. */
export const COURSE_TINT: Record<IconName, string> = {
  code: 'from-brand-100 to-brand-50 text-brand-700',
  python: 'from-gold-100 to-gold-50 text-gold-700',
  web: 'from-sky-100 to-sky-50 text-sky-700',
  game: 'from-rose-100 to-rose-50 text-rose-600',
  robot: 'from-emerald-100 to-emerald-50 text-emerald-700',
  digital: 'from-violet-100 to-violet-50 text-violet-700',
  design: 'from-orange-100 to-orange-50 text-orange-700',
}
