import { useEffect, useState } from 'react'
import { ArrowLeft, Briefcase, CalendarDays, Check, Clock, Link2, MapPin, Share2, Wallet } from 'lucide-react'
import { AxiosError } from 'axios'
import { Link, useLocation, useParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useCareersVacancy } from '@/hooks/useCareers'
import { extractErrorMessage } from '@/lib/apiError'
import type { PublicVacancy } from '@/types/careers'

import { ApplyForm } from './ApplyForm'
import { COMPANY } from './content'
import { formatPublished, formatSalary } from './format'
import { absoluteUrl, useDocumentMeta } from './useDocumentMeta'
import { Fact, vacancyPath } from './VacancyCard'

const SCHEMA_EMPLOYMENT: Record<string, string> = {
  full_time: 'FULL_TIME', part_time: 'PART_TIME', project: 'CONTRACTOR', internship: 'INTERN',
}

function jobPosting(v: PublicVacancy, url: string): Record<string, unknown> {
  const data: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'JobPosting',
    title: v.title,
    description: [v.description, ...v.responsibilities, ...v.requirements].filter(Boolean).join('\n'),
    datePosted: v.published_at,
    employmentType: SCHEMA_EMPLOYMENT[v.employment_type],
    hiringOrganization: { '@type': 'Organization', name: COMPANY.name },
    url,
  }
  if (v.closes_on) data.validThrough = v.closes_on
  if (v.location) data.jobLocation = { '@type': 'Place', address: { '@type': 'PostalAddress', addressLocality: v.location } }
  if (v.work_format === 'remote') data.jobLocationType = 'TELECOMMUTE'
  if (v.salary) {
    data.baseSalary = {
      '@type': 'MonetaryAmount', currency: v.salary.currency,
      value: { '@type': 'QuantitativeValue', minValue: v.salary.min ?? undefined, maxValue: v.salary.max ?? undefined, unitText: 'MONTH' },
    }
  }
  return data
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li key={item} className="flex gap-2.5 text-ink-secondary">
            <Check className="mt-1 size-4 shrink-0 text-brand-600" aria-hidden />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function ShareButton({ title, url }: { title: string; url: string }) {
  const [copied, setCopied] = useState(false)
  const share = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title, url })
        return
      } catch {
        // Пользователь закрыл окно «Поделиться» — копируем ссылку как запасной путь.
      }
    }
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2500)
    } catch {
      window.prompt('Скопируйте ссылку на вакансию', url)
    }
  }
  return (
    <Button type="button" variant="secondary" className="w-full" leftIcon={copied ? <Link2 className="size-4" aria-hidden /> : <Share2 className="size-4" aria-hidden />} onClick={() => void share()}>
      {copied ? 'Ссылка скопирована' : 'Поделиться'}
    </Button>
  )
}

function Unavailable({ title, closed }: { title?: string; closed: boolean }) {
  useDocumentMeta({ title: `${closed ? 'Вакансия закрыта' : 'Вакансия не найдена'} — ${COMPANY.siteName}`, noindex: true })
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center sm:px-6">
      <h1 className="text-2xl font-semibold text-ink">{closed ? `«${title}» — приём откликов закрыт` : 'Вакансия не найдена'}</h1>
      <p className="mt-3 text-ink-secondary">
        {closed ? 'Эта вакансия больше не принимает отклики. Посмотрите другие открытые вакансии — возможно, вам подойдёт одна из них.'
          : 'Возможно, ссылка устарела или вакансия ещё не опубликована.'}
      </p>
      <Link to="/careers" className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600">
        Все вакансии
      </Link>
    </div>
  )
}

/** /careers/vacancies/:slug — страница вакансии с уникальным адресом, SEO-метаданными и откликом. */
export function VacancyPage() {
  const slug = useParams().slug ?? ''
  const vacancy = useCareersVacancy(slug)
  const { hash } = useLocation()

  useEffect(() => {
    if (hash === '#apply' && vacancy.data) document.getElementById('apply')?.scrollIntoView?.({ behavior: 'smooth' })
  }, [hash, vacancy.data])

  if (vacancy.isPending) return <LoadingState label="Загружаем вакансию…" />
  if (vacancy.isError) {
    const error = vacancy.error
    if (error instanceof AxiosError && (error.response?.status === 404 || error.response?.status === 410)) {
      const data = error.response.data as { title?: string }
      return <Unavailable closed={error.response.status === 410} title={data?.title} />
    }
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <ErrorState message={extractErrorMessage(error)} onRetry={() => void vacancy.refetch()} />
      </div>
    )
  }
  return <VacancyContent vacancy={vacancy.data} />
}

function VacancyContent({ vacancy: v }: { vacancy: PublicVacancy }) {
  const url = absoluteUrl(vacancyPath(v.slug))
  const salary = formatSalary(v.salary)
  useDocumentMeta({
    title: `${v.title} — вакансия ${COMPANY.name}`,
    description: v.summary || `${v.title}${v.location ? `, ${v.location}` : ''}. ${v.work_format_label}, ${v.employment_type_label.toLowerCase()}. Откликнуться без регистрации.`,
    url,
    jsonLd: jobPosting(v, url),
  })

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Link to="/careers" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-secondary hover:text-brand-700">
        <ArrowLeft className="size-4" aria-hidden />
        Все вакансии
      </Link>
      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_20rem]">
        <article className="card card-body min-w-0 sm:p-8">
          {v.department ? <p className="text-sm font-medium uppercase tracking-wide text-brand-700">{v.department}</p> : null}
          <h1 className="mt-1 text-2xl font-bold text-ink sm:text-3xl">{v.title}</h1>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
            {v.location ? <Fact icon={MapPin}>{v.location}</Fact> : null}
            <Fact icon={Briefcase}>{v.work_format_label}</Fact>
            <Fact icon={Clock}>{v.employment_type_label}</Fact>
            {salary ? <Fact icon={Wallet}>{salary}</Fact> : null}
          </div>
          {v.summary ? <p className="mt-5 text-lg text-ink">{v.summary}</p> : null}
          {v.description ? <p className="mt-4 whitespace-pre-line leading-relaxed text-ink-secondary">{v.description}</p> : null}
          <Section title="Обязанности" items={v.responsibilities} />
          <Section title="Требования" items={v.requirements} />
          <Section title="Будет плюсом" items={v.nice_to_have} />
          <Section title="Условия работы" items={v.conditions} />
          {v.selection_stages.length ? (
            <section className="mt-8">
              <h2 className="text-lg font-semibold text-ink">Этапы отбора</h2>
              <ol className="mt-3 space-y-2">
                {v.selection_stages.map((stage, index) => (
                  <li key={stage} className="flex items-center gap-3 text-ink-secondary">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-brand-50 text-sm font-semibold text-brand-700">{index + 1}</span>
                    {stage}
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          <section id="apply" className="mt-10 scroll-mt-24 border-t border-border pt-8">
            <h2 className="text-xl font-semibold text-ink">Откликнуться на вакансию</h2>
            <p className="mb-5 mt-1 text-sm text-ink-secondary">Заполните короткую анкету — обязательны только ФИО, телефон и email.</p>
            <ApplyForm slug={v.slug} vacancyTitle={v.title} />
          </section>
        </article>
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="card card-body space-y-4">
            <dl className="space-y-3 text-sm">
              {salary ? <div><dt className="text-ink-muted">Зарплата</dt><dd className="font-semibold text-ink">{salary}</dd></div> : null}
              <div><dt className="text-ink-muted">Формат работы</dt><dd className="text-ink">{v.work_format_label}</dd></div>
              <div><dt className="text-ink-muted">Тип занятости</dt><dd className="text-ink">{v.employment_type_label}</dd></div>
              {v.location ? <div><dt className="text-ink-muted">Место работы</dt><dd className="text-ink">{v.location}</dd></div> : null}
              <div className="flex items-center gap-1.5 text-ink-secondary"><CalendarDays className="size-4" aria-hidden />Опубликовано {formatPublished(v.published_at)}</div>
              {v.closes_on ? <div className="text-ink-secondary">Приём откликов до {formatPublished(v.closes_on)}</div> : null}
            </dl>
            <a href="#apply" className="flex h-11 w-full items-center justify-center rounded-lg bg-brand-500 text-sm font-semibold text-white hover:bg-brand-600">
              Откликнуться
            </a>
            <ShareButton title={v.title} url={url} />
          </div>
        </aside>
      </div>
    </div>
  )
}
