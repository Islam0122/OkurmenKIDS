import { ArrowRight, Briefcase, Clock, MapPin, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { PublicVacancyCard } from '@/types/careers'

import { formatPublished, formatSalary } from './format'

export function vacancyPath(slug: string): string {
  return `/careers/vacancies/${slug}`
}

export function Fact({ icon: Icon, children }: { icon: typeof MapPin; children: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink-secondary">
      <Icon className="size-4 shrink-0 text-ink-muted" aria-hidden />
      {children}
    </span>
  )
}

/** Карточка вакансии в каталоге: всё главное и две кнопки — подробнее и откликнуться. */
export function VacancyCard({ vacancy: v }: { vacancy: PublicVacancyCard }) {
  const salary = formatSalary(v.salary)
  return (
    <article className="card card-body flex flex-col gap-3 transition-shadow hover:shadow-md" aria-labelledby={`vac-${v.slug}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {v.department ? <p className="text-xs font-medium uppercase tracking-wide text-brand-700">{v.department}</p> : null}
          <h3 id={`vac-${v.slug}`} className="mt-0.5 text-lg font-semibold text-ink">
            <Link to={vacancyPath(v.slug)} className="hover:text-brand-700">{v.title}</Link>
          </h3>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700">
          <span className="size-1.5 rounded-full bg-current" aria-hidden />
          Приём откликов открыт
        </span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {v.location ? <Fact icon={MapPin}>{v.location}</Fact> : null}
        <Fact icon={Briefcase}>{v.work_format_label}</Fact>
        <Fact icon={Clock}>{v.employment_type_label}</Fact>
        {salary ? <Fact icon={Wallet}>{salary}</Fact> : null}
      </div>
      {v.summary ? <p className="text-sm text-ink-secondary">{v.summary}</p> : null}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-1">
        <p className="text-xs text-ink-muted">Опубликовано {formatPublished(v.published_at)}</p>
        <div className="flex gap-2">
          <Link to={vacancyPath(v.slug)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-brand-200 px-3 text-sm font-medium text-brand-700 hover:bg-brand-50">
            Подробнее
          </Link>
          <Link to={`${vacancyPath(v.slug)}#apply`} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-500 px-3 text-sm font-medium text-white hover:bg-brand-600">
            Откликнуться
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      </div>
    </article>
  )
}
