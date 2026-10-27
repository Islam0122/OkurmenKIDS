import { useEffect, useState, type ReactNode } from 'react'
import { ArrowLeft, ArrowRight, Briefcase, CalendarDays, Clock, Link2, MapPin, Share2, Wallet } from 'lucide-react'
import { AxiosError } from 'axios'
import { Link, useLocation, useParams } from 'react-router-dom'

import { useCareersVacancy } from '@/hooks/useCareers'
import { extractErrorMessage } from '@/lib/apiError'
import type { PublicVacancy } from '@/types/careers'

import { ApplyForm } from './ApplyForm'
import { Eyebrow } from './Eyebrow'
import { GlassesMark } from './Photo'
import { scrollToSection } from './scroll'
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
    <section className="border-t border-ok-line py-8">
      <h2 className="text-xl font-extrabold text-ok-indigo">{title}</h2>
      <ul className="mt-4 space-y-3">
        {items.map((item) => (
          <li key={item} className="grid grid-cols-[auto_1fr] gap-3 text-[17px] leading-relaxed text-ok-ink/85">
            <span className="mt-[0.7em] size-2 rounded-full bg-ok-amber" aria-hidden />
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
  const Icon = copied ? Link2 : Share2
  return (
    <button type="button" onClick={() => void share()}
      className="flex h-12 w-full items-center justify-center gap-2 rounded-full border-2 border-ok-indigo/15 text-[15px] font-bold text-ok-indigo transition-colors hover:border-ok-indigo/40 hover:bg-ok-paper">
      <Icon className="size-4" aria-hidden />
      {copied ? 'Ссылка скопирована' : 'Поделиться'}
    </button>
  )
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-3xl px-5 py-20 text-center sm:px-8">{children}</div>
}

function Unavailable({ title, closed }: { title?: string; closed: boolean }) {
  useDocumentMeta({ title: `${closed ? 'Вакансия закрыта' : 'Вакансия не найдена'} — ${COMPANY.siteName}`, noindex: true })
  return (
    <Shell>
      <div className="mx-auto w-40 opacity-30" aria-hidden><GlassesMark stroke="var(--color-ok-indigo)" /></div>
      <h1 className="mt-6 text-3xl font-extrabold text-ok-indigo">{closed ? `«${title}» — приём откликов закрыт` : 'Вакансия не найдена'}</h1>
      <p className="mx-auto mt-4 max-w-xl text-lg text-ok-muted">
        {closed ? 'Эта вакансия больше не принимает отклики. Посмотрите другие открытые вакансии — возможно, вам подойдёт одна из них.'
          : 'Возможно, ссылка устарела или вакансия ещё не опубликована.'}
      </p>
      <Link to="/careers#vacancies" className="mt-8 inline-flex h-12 items-center gap-2 rounded-full bg-ok-indigo px-6 font-bold text-white hover:bg-ok-indigo-soft">
        Все вакансии<ArrowRight className="size-4" aria-hidden />
      </Link>
    </Shell>
  )
}

/** /careers/vacancies/:slug — страница вакансии с уникальным адресом, SEO-метаданными и откликом. */
export function VacancyPage() {
  const slug = useParams().slug ?? ''
  const vacancy = useCareersVacancy(slug)
  const { hash } = useLocation()

  useEffect(() => {
    if (hash === '#apply' && vacancy.data) scrollToSection('apply')
  }, [hash, vacancy.data])

  if (vacancy.isPending) {
    return (
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8" aria-busy="true" aria-label="Загружаем вакансию…">
        <div className="h-4 w-32 rounded bg-ok-indigo-100 motion-safe:animate-pulse" />
        <div className="mt-5 h-12 w-2/3 rounded bg-ok-indigo-100 motion-safe:animate-pulse" />
        <div className="mt-4 h-5 w-1/2 rounded bg-ok-indigo-50 motion-safe:animate-pulse" />
        <div className="mt-12 h-64 rounded-[28px] bg-white motion-safe:animate-pulse" />
      </div>
    )
  }
  if (vacancy.isError) {
    const error = vacancy.error
    if (error instanceof AxiosError && (error.response?.status === 404 || error.response?.status === 410)) {
      const data = error.response.data as { title?: string }
      return <Unavailable closed={error.response.status === 410} title={data?.title} />
    }
    return (
      <Shell>
        <h1 className="text-3xl font-extrabold text-ok-indigo">Не удалось загрузить вакансию</h1>
        <p className="mt-4 text-lg text-ok-muted">{extractErrorMessage(error, 'Проверьте соединение и попробуйте ещё раз.')}</p>
        <button type="button" onClick={() => void vacancy.refetch()} className="mt-8 h-12 rounded-full bg-ok-indigo px-6 font-bold text-white hover:bg-ok-indigo-soft">Повторить</button>
      </Shell>
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
    <>
      <header className="relative overflow-hidden border-b border-ok-line">
        <div className="absolute -right-20 -top-10 hidden w-[520px] opacity-[0.06] lg:block" aria-hidden><GlassesMark stroke="var(--color-ok-indigo)" /></div>
        <div className="relative mx-auto max-w-7xl px-5 pb-12 pt-8 sm:px-8 lg:pb-16 lg:pt-12">
          <Link to="/careers#vacancies" className="inline-flex items-center gap-1.5 text-[15px] font-semibold text-ok-muted hover:text-ok-indigo">
            <ArrowLeft className="size-4" aria-hidden />
            Все вакансии
          </Link>
          <div className="mt-8">{v.department ? <Eyebrow>{v.department}</Eyebrow> : null}</div>
          <h1 className="mt-4 max-w-4xl text-4xl font-extrabold leading-[1.06] tracking-[-0.03em] text-ok-indigo sm:text-5xl lg:text-6xl">{v.title}</h1>
          <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
            {v.location ? <Fact icon={MapPin}>{v.location}</Fact> : null}
            <Fact icon={Briefcase}>{v.work_format_label}</Fact>
            <Fact icon={Clock}>{v.employment_type_label}</Fact>
            {salary ? <Fact icon={Wallet}>{salary}</Fact> : null}
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-12 sm:px-8 lg:grid-cols-[1fr_22rem] lg:gap-16 lg:py-16">
        <article className="min-w-0">
          {v.summary ? <p className="text-2xl font-semibold leading-snug text-ok-ink">{v.summary}</p> : null}
          {v.description ? <p className="mt-5 whitespace-pre-line text-[17px] leading-relaxed text-ok-ink/80">{v.description}</p> : null}
          <div className="mt-8">
            <Section title="Обязанности" items={v.responsibilities} />
            <Section title="Требования" items={v.requirements} />
            <Section title="Будет плюсом" items={v.nice_to_have} />
            <Section title="Условия работы" items={v.conditions} />
            {v.selection_stages.length ? (
              <section className="border-t border-ok-line py-8">
                <h2 className="text-xl font-extrabold text-ok-indigo">Этапы отбора</h2>
                <ol className="mt-5 space-y-4">
                  {v.selection_stages.map((stage, index) => (
                    <li key={stage} className="flex items-center gap-4 text-[17px] text-ok-ink/85">
                      <span className={index === 0 ? 'flex size-10 shrink-0 items-center justify-center rounded-full bg-ok-amber font-extrabold text-ok-indigo-deep'
                        : 'flex size-10 shrink-0 items-center justify-center rounded-full border-2 border-ok-indigo font-extrabold text-ok-indigo'}>{index + 1}</span>
                      {stage}
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}
          </div>
          <section id="apply" aria-labelledby="apply-title" className="mt-6 scroll-mt-24 rounded-[28px] bg-white p-6 shadow-[0_24px_60px_-40px_rgba(23,14,69,0.35)] ring-1 ring-ok-line sm:p-10">
            <Eyebrow>Отклик</Eyebrow>
            <h2 id="apply-title" className="mt-4 text-3xl font-extrabold tracking-[-0.02em] text-ok-indigo">Откликнуться на вакансию</h2>
            <p className="mb-8 mt-2 text-[17px] text-ok-muted">Заполните короткую анкету — обязательны только ФИО, телефон и email. Регистрация не нужна.</p>
            <ApplyForm slug={v.slug} vacancyTitle={v.title} />
          </section>
        </article>
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <div className="rounded-[28px] bg-ok-indigo p-7 text-white">
            <dl className="space-y-4 text-[15px]">
              {salary ? <div><dt className="text-white/60">Зарплата</dt><dd className="mt-0.5 text-xl font-extrabold">{salary}</dd></div> : null}
              <div><dt className="text-white/60">Формат работы</dt><dd className="mt-0.5 font-bold">{v.work_format_label}</dd></div>
              <div><dt className="text-white/60">Тип занятости</dt><dd className="mt-0.5 font-bold">{v.employment_type_label}</dd></div>
              {v.location ? <div><dt className="text-white/60">Место работы</dt><dd className="mt-0.5 font-bold">{v.location}</dd></div> : null}
            </dl>
            <p className="mt-6 flex items-center gap-2 border-t border-white/15 pt-5 text-sm text-white/70">
              <CalendarDays className="size-4" aria-hidden />Опубликовано {formatPublished(v.published_at)}
            </p>
            {v.closes_on ? <p className="mt-1 text-sm text-white/70">Приём откликов до {formatPublished(v.closes_on)}</p> : null}
            <a href="#apply" onClick={(e) => { e.preventDefault(); scrollToSection('apply') }}
              className="mt-6 flex h-12 w-full items-center justify-center rounded-full bg-ok-amber text-[15px] font-extrabold text-ok-indigo-deep transition-colors hover:bg-ok-amber/90">
              Откликнуться
            </a>
          </div>
          <div className="mt-3"><ShareButton title={v.title} url={url} /></div>
        </aside>
      </div>
    </>
  )
}
