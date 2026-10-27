import { ArrowUpRight, Briefcase, Clock, MapPin } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { PublicVacancyCard } from '@/types/careers'

import { formatPublished, formatSalary } from './format'

export function vacancyPath(slug: string): string {
  return `/careers/vacancies/${slug}`
}

export function Fact({ icon: Icon, children }: { icon: typeof MapPin; children: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[15px] text-ok-muted">
      <Icon className="size-4 shrink-0 text-ok-indigo/50" aria-hidden />
      {children}
    </span>
  )
}

/** Строка каталога вакансий: всё главное и два действия — подробнее и откликнуться. */
export function VacancyCard({ vacancy: v }: { vacancy: PublicVacancyCard }) {
  const salary = formatSalary(v.salary)
  const path = vacancyPath(v.slug)
  return (
    <article aria-labelledby={`vac-${v.slug}`}
      className="group relative grid gap-5 border-t border-ok-line py-7 transition-colors first:border-t-0 md:grid-cols-[1fr_auto] md:gap-10 md:px-6 md:hover:bg-ok-paper lg:py-8">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] font-bold uppercase tracking-[0.14em]">
          {v.department ? <span className="text-ok-indigo">{v.department}</span> : null}
          <span className="font-semibold normal-case tracking-normal text-ok-muted">Опубликовано {formatPublished(v.published_at)}</span>
        </div>
        <h3 id={`vac-${v.slug}`} className="mt-2 text-2xl font-extrabold tracking-[-0.01em] text-ok-ink">
          <Link to={path} className="transition-colors hover:text-ok-indigo-soft">{v.title}</Link>
        </h3>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
          {v.location ? <Fact icon={MapPin}>{v.location}</Fact> : null}
          <Fact icon={Briefcase}>{v.work_format_label}</Fact>
          <Fact icon={Clock}>{v.employment_type_label}</Fact>
        </div>
        {v.summary ? <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ok-muted">{v.summary}</p> : null}
      </div>
      <div className="flex flex-col gap-4 md:items-end md:justify-between">
        {salary ? <p className="text-lg font-extrabold text-ok-indigo">{salary}</p> : <span className="hidden md:block" />}
        <div className="flex gap-2">
          <Link to={path} className="inline-flex h-11 items-center rounded-full border-2 border-ok-indigo/15 px-5 text-[15px] font-bold text-ok-indigo transition-colors hover:border-ok-indigo/40 hover:bg-white">
            Подробнее
          </Link>
          <Link to={`${path}#apply`} aria-label={`Откликнуться на вакансию «${v.title}»`}
            className="inline-flex h-11 items-center gap-1.5 rounded-full bg-ok-indigo px-5 text-[15px] font-bold text-white transition-colors hover:bg-ok-indigo-soft">
            Откликнуться
            <ArrowUpRight className="size-4 transition-transform motion-safe:group-hover:-translate-y-0.5 motion-safe:group-hover:translate-x-0.5" aria-hidden />
          </Link>
        </div>
      </div>
    </article>
  )
}

export function VacancySkeleton() {
  return (
    <div className="grid gap-4 border-t border-ok-line py-8 first:border-t-0 md:grid-cols-[1fr_auto] md:px-6" aria-hidden>
      <div className="space-y-3">
        <div className="h-3 w-28 rounded bg-ok-indigo-100 motion-safe:animate-pulse" />
        <div className="h-6 w-2/3 rounded bg-ok-indigo-100 motion-safe:animate-pulse" />
        <div className="h-4 w-1/2 rounded bg-ok-indigo-50 motion-safe:animate-pulse" />
      </div>
      <div className="h-11 w-56 rounded-full bg-ok-indigo-50 motion-safe:animate-pulse" />
    </div>
  )
}
