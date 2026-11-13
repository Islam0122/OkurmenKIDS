import { CalendarRange, CheckCircle2, Clock, Layers, Tag, Users } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { COURSE_ICONS, COURSE_TINT } from '@/components/cards/CourseIcon'
import { ProjectCard } from '@/components/cards/ProjectCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { PageHero } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { crumbsLd, detailDescription, detailTitle, Seo } from '@/components/shared/Seo'
import { SmartImage } from '@/components/shared/SmartImage'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { RichText } from '@/features/content/RichText'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { EnrollmentForm } from '@/features/enrollment/EnrollmentForm'
import { isNotFound, useCourse } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { CourseDetail } from '@/types/api'
import { cn } from '@/utils/cn'
import { ageRange, excerpt } from '@/utils/format'
import { absoluteUrl, mediaUrl } from '@/utils/media'
import { BRAND } from '@/app/config/site'
import { useItemLangs } from '@/hooks/queries'

export function CourseDetailPage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useCourse(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <CourseView course={data} />
}

export function CourseView({ course, preview }: { course: CourseDetail; preview?: boolean }) {
  const { t, path, lang } = useI18n()
  const langs = useItemLangs('courses', course.slug, preview ? undefined : course)
  const ageMin = Number(course.age_min) || undefined
  const ageMax = Number(course.age_max) || undefined
  const Icon = COURSE_ICONS[course.icon] ?? COURSE_ICONS.code
  const age = ageRange(t, course.age_min, course.age_max)
  const facts = [
    age && { icon: Users, label: t('courses.age'), value: age },
    course.duration && { icon: CalendarRange, label: t('courses.duration'), value: course.duration },
    course.lessons && { icon: Layers, label: t('courses.lessons'), value: String(course.lessons) },
    // «Формат занятий» is free text in the visitor's language: line breaks are kept, and a long or
    // multi-line text takes the whole row instead of squeezing into a small tile.
    course.schedule && { icon: Clock, label: t('courses.schedule'), value: course.schedule, text: true },
    course.price && { icon: Tag, label: t('courses.price'), value: course.price },
  ].filter(Boolean) as { icon: typeof Users; label: string; value: string; text?: boolean }[]
  const isLong = (value: string) => value.includes('\n') || value.length > 40

  return (
    <>
      <Seo
        title={detailTitle(lang, 'courses', course.title, course.seo_title)}
        description={detailDescription(lang, 'courses', course.tagline || course.body, course.seo_description)}
        image={course.cover?.url}
        noindex={preview}
        langs={langs}
        jsonLd={[
          crumbsLd(lang, 'courses', { name: course.title, slug: course.slug }),
          {
            '@context': 'https://schema.org',
            '@type': 'Course',
            name: course.title,
            description: course.tagline || excerpt(course.body, 300),
            url: absoluteUrl(path(`/courses/${course.slug}`)),
            inLanguage: lang,
            provider: { '@type': 'EducationalOrganization', '@id': absoluteUrl('/#organization'), name: BRAND.name, url: absoluteUrl('/') },
            ...(course.cover?.url ? { image: absoluteUrl(mediaUrl(course.cover.url) ?? course.cover.url) } : {}),
            ...(ageMin || ageMax ? { audience: { '@type': 'PeopleAudience', audienceType: 'children', ...(ageMin ? { suggestedMinAge: ageMin } : {}), ...(ageMax ? { suggestedMaxAge: ageMax } : {}) } } : {}),
            ...(course.subjects.length ? { about: course.subjects } : {}),
            ...(course.outcomes.length ? { teaches: course.outcomes } : {}),
          },
        ]}
      />
      <PageHero title={course.title} text={course.tagline} crumbs={[{ label: t('nav.courses'), to: '/courses' }, { label: course.title }]}>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
          <EnrollButton size="lg" course={course.slug} />
          {course.subjects.length ? (
            <ul className="flex flex-wrap gap-2">
              {course.subjects.map((s) => <li key={s} className="rounded-full bg-white px-3 py-1.5 text-sm font-bold text-brand-700 shadow-soft">{s}</li>)}
            </ul>
          ) : null}
        </div>
      </PageHero>

      <div className="container-page grid gap-10 py-12 lg:grid-cols-[1fr_380px] lg:gap-14 lg:py-16">
        <div className="min-w-0 space-y-14">
          <Reveal className={cn('overflow-hidden rounded-[2rem] bg-gradient-to-br', COURSE_TINT[course.icon])}>
            {course.cover ? (
              <SmartImage image={course.cover} alt={course.title} priority sizes="(min-width: 1024px) 60vw, 100vw" className="aspect-[16/8] w-full" />
            ) : (
              <div className="flex aspect-[16/7] items-center justify-center"><Icon className="size-28 opacity-70" strokeWidth={1.2} aria-hidden /></div>
            )}
          </Reveal>

          {facts.length ? (
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {facts.map((f) => (
                <div key={f.label} className={cn('rounded-2xl border border-line bg-white p-4', f.text && isLong(f.value) && 'col-span-full')}>
                  <dt className="flex items-center gap-2 text-xs font-bold tracking-wide text-muted uppercase"><f.icon className="size-4 text-brand-400" aria-hidden />{f.label}</dt>
                  <dd className={cn('mt-1.5', f.text ? 'whitespace-pre-line break-words' : '', f.text && isLong(f.value) ? 'text-base leading-relaxed font-semibold text-ink-soft' : 'font-display text-lg font-extrabold')}>{f.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {course.body ? (
            <section>
              <h2 className="mb-5 text-2xl font-black sm:text-3xl">{t('courses.about')}</h2>
              <RichText source={course.body} />
            </section>
          ) : null}

          {course.outcomes.length ? (
            <section>
              <h2 className="mb-6 text-2xl font-black sm:text-3xl">{t('courses.outcomes')}</h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {course.outcomes.map((o, i) => (
                  <Reveal as="li" key={i} delay={i * 0.04} className="flex items-start gap-3 rounded-2xl bg-surface-purple p-4">
                    <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-brand-600" aria-hidden />
                    <span className="font-semibold text-ink-soft">{o}</span>
                  </Reveal>
                ))}
              </ul>
            </section>
          ) : null}

          {course.curriculum.length ? (
            <section>
              <h2 className="mb-6 text-2xl font-black sm:text-3xl">{t('courses.curriculum')}</h2>
              <ol className="space-y-3">
                {course.curriculum.map((m, i) => (
                  <Reveal as="li" key={i} delay={i * 0.04} className="flex gap-4 rounded-2xl border border-line bg-white p-5">
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-800 font-display font-black text-gold-400">{String(i + 1).padStart(2, '0')}</span>
                    <div>
                      <h3 className="font-extrabold">{m.title}</h3>
                      {m.text ? <p className="mt-1 text-[15px] text-muted">{m.text}</p> : null}
                    </div>
                  </Reveal>
                ))}
              </ol>
            </section>
          ) : null}
        </div>

        <aside className="lg:sticky lg:top-28 lg:self-start">
          <div className="card p-6 sm:p-7">
            <h2 className="text-xl font-black">{t('courses.enrollTitle')}</h2>
            <p className="mt-1.5 mb-5 text-sm text-muted">{t('courses.enrollText')}</p>
            {preview ? <p className="text-sm text-muted">—</p> : <EnrollmentForm defaultCourse={course.slug} compact />}
          </div>
        </aside>
      </div>

      {course.projects.length ? (
        <section className="section bg-surface-soft">
          <div className="container-page">
            <SectionHeader title={t('courses.projects')} link={{ to: course.project_category ? `/projects?category=${course.project_category}` : '/projects', label: t('cta.allProjects') }} />
            <CardGrid items={course.projects} keyOf={(p) => p.key} render={(p) => <ProjectCard project={p} />} />
          </div>
        </section>
      ) : null}
    </>
  )
}
