import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ProgramArt } from '@/components/home/ProgramArt'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { useEnroll } from '@/features/enrollment/EnrollmentProvider'
import { PROGRAMS, programCourse, programTarget } from '@/features/programs/programs'
import { useProjects } from '@/hooks/queries'
import { useI18n, type MessageKey } from '@/i18n'
import type { CourseCard } from '@/types/api'
import { ageRange } from '@/utils/format'

const card =
  'group relative flex h-full flex-col overflow-hidden rounded-[1.25rem] border border-[#ece7f8] bg-white shadow-[0_10px_30px_-18px_rgb(37_16_95/0.35)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_24px_44px_-20px_rgb(37_16_95/0.45)] focus-within:-translate-y-1 focus-within:ring-4 focus-within:ring-brand-200'
/** «Подробнее» stretched over the whole card (valid markup: the heading stays outside the link/button). */
const action = 'mt-4 inline-flex items-center gap-1.5 self-start text-[15px] font-bold text-kids-primary outline-none after:absolute after:inset-0 after:content-[\'\']'

/**
 * «Популярные курсы» — the academy's six directions (features/programs).
 * Age label, link and data come from the course published in the CMS when it
 * exists; nothing (duration, price, age) is shown that the CMS does not hold.
 */
export function ProgramsSection({ courses, title }: { courses: CourseCard[]; title?: string }) {
  const { t, path } = useI18n()
  const { openEnroll } = useEnroll()
  const projects = useProjects({ page_size: 1 })
  return (
    <section id="programs" className="scroll-mt-24 pt-12 pb-6 sm:pt-14 lg:pt-16 lg:pb-8">
      <div className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow={t('home.programs.eyebrow')}
          title={title || t('home.programs.title')}
          text={t('home.programs.text')}
          link={{ to: '/courses', label: t('cta.allCourses') }}
        />
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6">
          {PROGRAMS.map((program, i) => {
            const course = programCourse(program, courses)
            const target = programTarget(program, courses, projects.data?.counts ?? {})
            const name = t(`home.programs.${program.id}.name` as MessageKey)
            const age = course ? ageRange(t, course.age_min, course.age_max) : null
            const label = (
              <>
                {t('cta.more')} <ArrowRight className="size-4 transition group-hover:translate-x-1" aria-hidden />
              </>
            )
            return (
              <Reveal as="li" key={program.id} delay={i * 0.05} className="h-full">
                <div className={card}>
                <div className="relative aspect-[2/1] overflow-hidden">
                  <div className="size-full transition duration-500 group-hover:scale-[1.04]"><ProgramArt id={program.id} /></div>
                  {age ? <span className="absolute top-3 left-3 rounded-full bg-white px-3 py-1 text-xs font-bold text-kids-primary shadow-soft">{age}</span> : null}
                </div>
                <div className="flex flex-1 flex-col p-5 sm:p-6">
                  <h3 className="font-display text-xl font-extrabold text-kids-text">{course?.title ?? name}</h3>
                  <p className="mt-1.5 flex-1 text-[15px] leading-snug text-kids-muted">{course?.tagline || t(`home.programs.${program.id}.text` as MessageKey)}</p>
                  {target.kind === 'enroll' ? (
                    // No course page yet: «Подробнее» opens the enrollment form to ask about this program.
                    <button type="button" onClick={() => openEnroll()} className={action} aria-label={`${name} — ${t('cta.more')}`}>{label}</button>
                  ) : (
                    <Link to={path(target.to)} className={action} aria-label={`${name} — ${t('cta.more')}`}>{label}</Link>
                  )}
                </div>
                </div>
              </Reveal>
            )
          })}
        </ul>
      </div>
    </section>
  )
}
