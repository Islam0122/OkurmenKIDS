import type { LucideIcon } from 'lucide-react'
import { Atom, Code2, Monitor, Server, Sparkles, Terminal } from 'lucide-react'

import type { CourseCard } from '@/types/api'

/** Project gallery categories (`/projects?category=…`, apps.projects). */
export type ProjectCategory = 'html-css' | 'javascript' | 'react' | 'python'

export interface Program {
  id: 'html' | 'python' | 'react' | 'fastapi' | 'vibe' | 'literacy'
  icon: LucideIcon
  /** Picks this program's page among the courses published in the CMS. */
  matches: (course: CourseCard) => boolean
  /** The project gallery filter with this program's student work, if any exists. */
  projectCategory?: ProjectCategory
  /** Tailwind classes of the icon tile — brand purple/gold only. */
  tone: string
}

const text = (course: CourseCard) => `${course.slug} ${course.title}`.toLowerCase()

/**
 * «Чему учатся дети» — the academy's directions. A card links to its course
 * page as soon as marketing publishes one in the CMS; until then it links to
 * real student projects of that technology, or opens the enrollment form to
 * ask about it. No course page or project count is ever assumed.
 */
export const PROGRAMS: Program[] = [
  {
    id: 'html',
    icon: Code2,
    matches: (c) => /html|css|javascript|\bjs\b|веб|web|frontend|фронтенд/.test(text(c)) && !/react/.test(text(c)),
    projectCategory: 'html-css',
    tone: 'bg-brand-800 text-gold-400',
  },
  {
    id: 'python',
    icon: Terminal,
    matches: (c) => /python|питон/.test(text(c)) && !/fastapi/.test(text(c)),
    projectCategory: 'python',
    tone: 'bg-gold-400 text-brand-900',
  },
  { id: 'react', icon: Atom, matches: (c) => /react/.test(text(c)), projectCategory: 'react', tone: 'bg-brand-600 text-white' },
  { id: 'fastapi', icon: Server, matches: (c) => /fastapi/.test(text(c)), tone: 'bg-brand-100 text-brand-800' },
  { id: 'vibe', icon: Sparkles, matches: (c) => /vibe|вайб/.test(text(c)), tone: 'bg-gold-100 text-brand-800' },
  {
    id: 'literacy',
    icon: Monitor,
    matches: (c) => /грамотн|сабаттуул|literacy|компьютер/.test(text(c)),
    tone: 'bg-surface-purple text-brand-700',
  },
]

/** Where a program card's «Подробнее» leads. */
export type ProgramTarget =
  | { kind: 'course'; to: string }
  | { kind: 'projects'; to: string }
  | { kind: 'enroll' }

export function programTarget(program: Program, courses: CourseCard[], projectCounts: Record<string, number>): ProgramTarget {
  const course = courses.find(program.matches)
  if (course) return { kind: 'course', to: `/courses/${course.slug}` }
  if (program.projectCategory && (projectCounts[program.projectCategory] ?? 0) > 0) {
    return { kind: 'projects', to: `/projects?category=${program.projectCategory}` }
  }
  return { kind: 'enroll' }
}
