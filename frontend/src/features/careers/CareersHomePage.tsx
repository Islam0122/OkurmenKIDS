import { useEffect, useState, type FormEvent } from 'react'
import { CheckCircle2, Search, SearchX } from 'lucide-react'
import { useLocation, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { useCareersFilters, useCareersVacancies } from '@/hooks/useCareers'
import { extractErrorMessage } from '@/lib/apiError'
import type { CareersOrdering } from '@/types/careers'
import { pluralize } from '@/utils/format'

import { BENEFITS, COMPANY, CONDITIONS } from './content'
import { absoluteUrl, useDocumentMeta } from './useDocumentMeta'
import { VacancyCard } from './VacancyCard'

const PAGE_SIZE = 12
const FILTER_KEYS = ['search', 'department', 'work_format', 'employment_type', 'location', 'ordering'] as const

const ORDERINGS: { value: CareersOrdering; label: string }[] = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
  { value: 'salary_desc', label: 'Зарплата: по убыванию' },
  { value: 'salary_asc', label: 'Зарплата: по возрастанию' },
  { value: 'title', label: 'По названию' },
]

/** /careers — главная карьерного сайта. Фильтры и страница хранятся в адресе,
 * поэтому ссылкой с подборкой можно поделиться. */
export function CareersHomePage() {
  const [params, setParams] = useSearchParams()
  const { hash } = useLocation()
  const filters = useCareersFilters()
  const page = Math.max(Number(params.get('page')) || 1, 1)
  const query = Object.fromEntries(FILTER_KEYS.map((key) => [key, params.get(key) ?? ''])) as Record<(typeof FILTER_KEYS)[number], string>
  const [search, setSearch] = useState(query.search)
  const list = useCareersVacancies({
    search: query.search || undefined, department: query.department || undefined, work_format: query.work_format || undefined,
    employment_type: query.employment_type || undefined, location: query.location || undefined,
    ordering: (query.ordering || 'newest') as CareersOrdering, page, page_size: PAGE_SIZE,
  })

  useDocumentMeta({
    title: `${COMPANY.siteName} — вакансии`,
    description: `${COMPANY.heroTitle}. ${COMPANY.tagline}. Актуальные вакансии и отклик без регистрации.`,
    url: absoluteUrl('/careers'),
  })

  useEffect(() => {
    if (!hash) return
    document.getElementById(hash.slice(1))?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }, [hash])

  const update = (changes: Partial<Record<(typeof FILTER_KEYS)[number] | 'page', string>>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next, { replace: false })
  }
  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    update({ search: search.trim() })
    document.getElementById('vacancies')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }
  const hasFilters = FILTER_KEYS.some((key) => key !== 'ordering' && query[key])
  const total = filters.data?.total

  return (
    <>
      <section className="bg-gradient-to-br from-brand-700 via-brand-600 to-brand-500 text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16 lg:py-20">
          <p className="text-sm font-medium uppercase tracking-wider text-white/80">{COMPANY.name}</p>
          <h1 className="mt-2 max-w-3xl text-3xl font-bold leading-tight sm:text-4xl lg:text-5xl">{COMPANY.heroTitle}</h1>
          <p className="mt-4 max-w-2xl text-base text-white/90 sm:text-lg">{COMPANY.heroText}</p>
          <form onSubmit={submitSearch} role="search" className="mt-8 flex max-w-2xl flex-col gap-2 rounded-2xl bg-white p-2 shadow-lg sm:flex-row">
            <label htmlFor="careers-search" className="sr-only">Поиск вакансий</label>
            <div className="flex min-w-0 flex-1 items-center gap-2 px-3">
              <Search className="size-5 shrink-0 text-ink-muted" aria-hidden />
              <input
                id="careers-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Должность или ключевое слово"
                className="h-11 w-full min-w-0 bg-transparent text-base text-ink outline-none placeholder:text-ink-muted"
                maxLength={100}
              />
            </div>
            <Button type="submit" size="lg">Найти вакансии</Button>
          </form>
          {typeof total === 'number' ? (
            <p className="mt-4 text-sm text-white/85">
              {total ? `Сейчас ${total} ${pluralize(total, 'открытая вакансия', 'открытые вакансии', 'открытых вакансий')}` : 'Открытых вакансий сейчас нет'}
            </p>
          ) : null}
        </div>
      </section>

      <section id="vacancies" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-10 sm:px-6">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-ink">Вакансии</h2>
            <p className="text-sm text-ink-secondary">Только актуальные вакансии, на которые идёт приём откликов.</p>
          </div>
        </div>
        <div className="mt-5 grid gap-3 rounded-2xl border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-5">
          <Select aria-label="Направление" value={query.department} onChange={(e) => update({ department: e.target.value })}
            placeholder="Все направления" options={(filters.data?.departments ?? []).map((d) => ({ value: d, label: d }))} />
          <Select aria-label="Формат работы" value={query.work_format} onChange={(e) => update({ work_format: e.target.value })}
            placeholder="Любой формат" options={filters.data?.work_formats ?? []} />
          <Select aria-label="Тип занятости" value={query.employment_type} onChange={(e) => update({ employment_type: e.target.value })}
            placeholder="Любая занятость" options={filters.data?.employment_types ?? []} />
          <Select aria-label="Город" value={query.location} onChange={(e) => update({ location: e.target.value })}
            placeholder="Все города" options={(filters.data?.locations ?? []).map((l) => ({ value: l, label: l }))} />
          <Select aria-label="Сортировка" value={query.ordering || 'newest'} onChange={(e) => update({ ordering: e.target.value === 'newest' ? '' : e.target.value })}
            options={ORDERINGS} />
        </div>
        {hasFilters ? (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink-secondary">
            {query.search ? <span>Поиск: «{query.search}»</span> : null}
            <button type="button" className="font-medium text-brand-700 hover:underline" onClick={() => { setSearch(''); setParams(new URLSearchParams()) }}>
              Сбросить фильтры
            </button>
          </div>
        ) : null}

        <div className="mt-6">
          {list.isPending ? (
            <LoadingState label="Загружаем вакансии…" />
          ) : list.isError ? (
            <ErrorState message={extractErrorMessage(list.error)} onRetry={() => void list.refetch()} />
          ) : list.data.results.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title={hasFilters ? 'По вашему запросу вакансий нет' : 'Открытых вакансий пока нет'}
              description={hasFilters ? 'Попробуйте изменить или сбросить фильтры.' : 'Загляните позже — новые вакансии появляются здесь сразу после публикации.'}
            />
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                {list.data.results.map((vacancy) => <VacancyCard key={vacancy.slug} vacancy={vacancy} />)}
              </div>
              <div className="mt-4">
                <Pagination page={page} pageSize={PAGE_SIZE} totalCount={list.data.count} onPageChange={(p) => update({ page: String(p) })} />
              </div>
            </>
          )}
        </div>
      </section>

      <section id="about" className="scroll-mt-20 border-y border-border bg-surface">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 lg:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold text-ink">О компании</h2>
            <p className="mt-3 text-base leading-relaxed text-ink-secondary">{COMPANY.about}</p>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">Условия работы</h3>
            <ul className="mt-3 space-y-2.5">
              {CONDITIONS.map((item) => (
                <li key={item} className="flex gap-2.5 text-sm text-ink-secondary">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section id="benefits" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-12 sm:px-6">
        <h2 className="text-2xl font-semibold text-ink">Почему у нас интересно работать</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {BENEFITS.map((benefit) => (
            <div key={benefit.title} className="card card-body">
              <span className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                <benefit.icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-3 font-semibold text-ink">{benefit.title}</h3>
              <p className="mt-1 text-sm text-ink-secondary">{benefit.text}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
