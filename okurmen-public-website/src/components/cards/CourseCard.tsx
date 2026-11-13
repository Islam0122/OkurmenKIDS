import { ArrowUpRight, CalendarRange, Clock, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/shared/Badge'
import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { CourseCard as Course } from '@/types/api'
import { cn } from '@/utils/cn'
import { ageRange } from '@/utils/format'

import { COURSE_ICONS, COURSE_TINT } from './CourseIcon'

/** `priority`: the first card of a list (the page's LCP image) loads eagerly. */
export function CourseCard({ course, priority }: { course: Course; priority?: boolean }) {
  const { t, path } = useI18n()
  const Icon = COURSE_ICONS[course.icon] ?? COURSE_ICONS.code
  const age = ageRange(t, course.age_min, course.age_max)
  return (
    <Link to={path(`/courses/${course.slug}`)} className="card card-hover group flex h-full flex-col overflow-hidden">
      <div className={cn('relative aspect-[16/10] overflow-hidden bg-gradient-to-br', COURSE_TINT[course.icon])}>
        {course.cover ? (
          <SmartImage image={course.cover} alt={course.title} priority={priority} className="size-full transition duration-700 group-hover:scale-105" />
        ) : (
          <div className="flex size-full items-center justify-center">
            <Icon className="size-20 opacity-80 transition duration-500 group-hover:scale-110 group-hover:rotate-3" strokeWidth={1.4} aria-hidden />
          </div>
        )}
        {course.is_featured ? <Badge tone="gold" className="absolute top-4 left-4">{t('courses.popular')}</Badge> : null}
      </div>
      <div className="flex flex-1 flex-col p-6">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-xl leading-tight font-extrabold">{course.title}</h3>
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700 transition group-hover:bg-gold-400 group-hover:text-brand-900">
            <ArrowUpRight className="size-5" aria-hidden />
          </span>
        </div>
        {course.tagline ? <p className="mt-2 line-clamp-2 text-[15px] text-muted">{course.tagline}</p> : null}
        <ul className="mt-auto flex flex-wrap gap-x-4 gap-y-2 pt-5 text-sm font-semibold text-ink-soft">
          {age ? <li className="flex items-center gap-1.5"><Users className="size-4 text-brand-400" aria-hidden />{age}</li> : null}
          {course.duration ? <li className="flex items-center gap-1.5"><CalendarRange className="size-4 text-brand-400" aria-hidden />{course.duration}</li> : null}
          {!course.duration && course.lessons ? <li className="flex items-center gap-1.5"><Clock className="size-4 text-brand-400" aria-hidden />{t('courses.lessonsCount', { count: course.lessons })}</li> : null}
        </ul>
      </div>
    </Link>
  )
}
