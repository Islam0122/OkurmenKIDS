import { ArrowRight, CalendarRange, Clock, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { COURSE_ICONS, COURSE_TINT } from '@/components/cards/CourseIcon'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { SmartImage } from '@/components/shared/SmartImage'
import { ErrorState } from '@/components/shared/States'
import { useCourses } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { CourseCard } from '@/types/api'
import { cn } from '@/utils/cn'
import { ageRange } from '@/utils/format'

/** The homepage shows at most this many courses; «Бардык курстар» leads to the full list. */
const MAX_COURSES = 6

/**
 * «Популярдуу курстар» — the courses published in the CMS («Сайт → Курсы»),
 * in the CMS order and in the visitor's language. Read from the existing
 * public endpoint GET /api/v1/public/site/courses/ (published + due only);
 * nothing about a course is written here.
 */
export function CoursesSection({ title }: { title?: string }) {
  const { t, lang } = useI18n()
  const { data, isPending, isError, error, refetch } = useCourses()
  const courses = (data?.results ?? []).slice(0, MAX_COURSES)

  // Nothing published (yet): no empty section on the homepage.
  if (!isPending && !isError && !courses.length) return null

  return (
    <section id="programs" className="scroll-mt-24 pt-12 pb-6 sm:pt-14 lg:pt-16 lg:pb-8" aria-busy={isPending || undefined}>
      <div className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow={t('home.programs.eyebrow')}
          title={title || t('home.programs.title')}
          text={t('home.programs.text')}
          link={{ to: '/courses', label: t('cta.allCourses') }}
        />
        {isPending ? (
          <CourseSkeletons label={t('state.loading')} />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : (
          <ul className="grid auto-rows-fr grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6" key={lang}>
            {courses.map((course, i) => (
              <Reveal as="li" key={course.slug} delay={Math.min(i, 5) * 0.05} className="h-full">
                <HomeCourseCard course={course} />
              </Reveal>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

/** One CMS course: cover, title, short description, age and length, «Кененирээк →» — all from the API. */
export function HomeCourseCard({ course }: { course: CourseCard }) {
  const { t, path } = useI18n()
  const Icon = COURSE_ICONS[course.icon] ?? COURSE_ICONS.code
  const age = ageRange(t, course.age_min, course.age_max)
  const length = course.duration
    ? { icon: CalendarRange, text: course.duration }
    : course.lessons
      ? { icon: Clock, text: t('courses.lessonsCount', { count: course.lessons }) }
      : null
  return (
    <Link
      to={path(`/courses/${course.slug}`)}
      aria-label={`${course.title} — ${t('cta.more')}`}
      className="group flex h-full flex-col overflow-hidden rounded-[1.25rem] border border-[#e7efe9] bg-white shadow-[0_10px_30px_-18px_rgb(22_101_52/0.35)] transition duration-300 hover:-translate-y-1 hover:border-kids-green/40 hover:shadow-[0_24px_44px_-20px_rgb(22_101_52/0.4)] focus-visible:-translate-y-1 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-kids-green/25"
    >
      <div className={cn('relative aspect-[16/10] overflow-hidden bg-gradient-to-br', COURSE_TINT[course.icon] ?? COURSE_TINT.code)}>
        {course.cover ? (
          <SmartImage
            image={course.cover}
            alt={course.title}
            sizes="(min-width: 1024px) 400px, (min-width: 640px) 50vw, 100vw"
            className="size-full transition duration-700 ease-out group-hover:scale-[1.04]"
          />
        ) : (
          // No cover in the CMS: the course's own icon on its tint, never a stock photo.
          <div className="flex size-full items-center justify-center" role="img" aria-label={course.title}>
            <Icon className="size-16 opacity-80" strokeWidth={1.4} aria-hidden />
          </div>
        )}
        {age ? (
          <span className="absolute top-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3 py-1 text-xs font-bold text-kids-green-deep shadow-soft backdrop-blur">
            <Users className="size-3.5" aria-hidden />{age}
          </span>
        ) : null}
      </div>

      <div className="flex flex-1 flex-col p-5 sm:p-6">
        <h3 className="line-clamp-2 font-display text-xl leading-snug font-extrabold text-kids-text">{course.title}</h3>
        {course.tagline ? <p className="mt-2 line-clamp-3 text-[15px] leading-relaxed text-kids-muted">{course.tagline}</p> : null}
        <div className="mt-auto pt-5">
          {length ? (
            <p className="mb-4 inline-flex items-center gap-1.5 rounded-lg bg-kids-green-soft px-2.5 py-1 text-sm font-semibold text-kids-green-deep">
              <length.icon className="size-4" aria-hidden />{length.text}
            </p>
          ) : null}
          <span className="flex items-center justify-between border-t border-[#eef2ef] pt-4 text-[15px] font-bold text-kids-green-deep">
            {t('cta.more')}
            <span className="grid size-9 place-items-center rounded-full bg-kids-green-soft transition duration-300 group-hover:bg-kids-green group-hover:text-white">
              <ArrowRight className="size-4 transition group-hover:translate-x-0.5" aria-hidden />
            </span>
          </span>
        </div>
      </div>
    </Link>
  )
}

function CourseSkeletons({ label }: { label: string }) {
  return (
    <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6" aria-label={label}>
      {Array.from({ length: 3 }, (_, i) => (
        <li key={i} className="overflow-hidden rounded-[1.25rem] border border-[#e7efe9] bg-white">
          <div className="aspect-[16/10] animate-pulse bg-kids-green-soft" />
          <div className="space-y-3 p-5 sm:p-6">
            <div className="h-6 w-3/4 animate-pulse rounded-md bg-surface-soft" />
            <div className="h-4 w-full animate-pulse rounded-md bg-surface-soft" />
            <div className="h-4 w-2/3 animate-pulse rounded-md bg-surface-soft" />
            <div className="h-9 w-full animate-pulse rounded-md bg-surface-soft" />
          </div>
        </li>
      ))}
    </ul>
  )
}
