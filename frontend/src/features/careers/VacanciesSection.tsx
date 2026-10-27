import { useState, type FormEvent } from 'react'
import { AlertTriangle, ChevronLeft, ChevronRight, Search, SlidersHorizontal, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { useCareersFilters, useCareersVacancies } from '@/hooks/useCareers'
import { extractErrorMessage } from '@/lib/apiError'
import type { CareersOrdering } from '@/types/careers'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/format'

import { Eyebrow } from './Eyebrow'
import { GlassesMark } from './Photo'
import { scrollToSection } from './scroll'
import { VacancyCard, VacancySkeleton } from './VacancyCard'

const PAGE_SIZE = 10
const FILTER_KEYS = ['search', 'department', 'work_format', 'employment_type', 'location', 'ordering'] as const
type Key = (typeof FILTER_KEYS)[number]

const ORDERINGS: { value: CareersOrdering; label: string }[] = [
  { value: 'newest', label: 'Сначала новые' },
  { value: 'oldest', label: 'Сначала старые' },
  { value: 'salary_desc', label: 'Зарплата: по убыванию' },
  { value: 'salary_asc', label: 'Зарплата: по возрастанию' },
  { value: 'title', label: 'По названию' },
]

function FilterSelect({ label, value, onChange, placeholder, options, active }: {
  label: string
  value: string
  active?: boolean
  onChange: (value: string) => void
  placeholder?: string
  options: { value: string; label: string }[]
}) {
  return (
    <label className="block min-w-0">
      <span className="sr-only">{label}</span>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
        className={cn('h-12 w-full min-w-0 cursor-pointer appearance-none truncate rounded-full border bg-white pl-4 pr-10 text-[15px] font-semibold text-ok-ink',
          'bg-[length:16px] bg-[right_14px_center] bg-no-repeat focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ok-indigo',
          (active ?? Boolean(value)) ? 'border-ok-indigo/50' : 'border-ok-line')}
        style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2327186d' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}>
        {placeholder ? <option value="">{placeholder}</option> : null}
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

/** Открытые вакансии из публичного API: только опубликованные, с открытым
 * приёмом откликов. Фильтры и страница — в адресе, подборкой можно поделиться. */
export function VacanciesSection() {
  const [params, setParams] = useSearchParams()
  const filters = useCareersFilters()
  const page = Math.max(Number(params.get('page')) || 1, 1)
  const query = Object.fromEntries(FILTER_KEYS.map((key) => [key, params.get(key) ?? ''])) as Record<Key, string>
  const [search, setSearch] = useState(query.search)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const list = useCareersVacancies({
    search: query.search || undefined, department: query.department || undefined, work_format: query.work_format || undefined,
    employment_type: query.employment_type || undefined, location: query.location || undefined,
    ordering: (query.ordering || 'newest') as CareersOrdering, page, page_size: PAGE_SIZE,
  })
  const total = filters.data?.total ?? 0
  const hasFilters = FILTER_KEYS.some((key) => key !== 'ordering' && query[key])
  const activeFilters = (['department', 'work_format', 'employment_type', 'location'] as const).filter((key) => query[key]).length

  const update = (changes: Partial<Record<Key | 'page', string>>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next, { replace: true, preventScrollReset: true })
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    update({ search: search.trim() })
  }
  const reset = () => {
    setSearch('')
    setParams(new URLSearchParams(), { replace: true, preventScrollReset: true })
  }
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / PAGE_SIZE)) : 1
  const goTo = (p: number) => {
    update({ page: p > 1 ? String(p) : '' })
    scrollToSection('vacancies')
  }
  // Фильтры нужны, только когда вакансий больше пары.
  const showFilters = total > 3 || hasFilters

  return (
    <section id="vacancies" aria-labelledby="vacancies-title" className="scroll-mt-20 bg-white">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Eyebrow>Вакансии</Eyebrow>
            <h2 id="vacancies-title" className="mt-5 text-3xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo sm:text-[2.6rem]">Открытые вакансии</h2>
          </div>
          <p className="text-lg text-ok-muted">
            {filters.data ? (total ? `${total} ${pluralize(total, 'вакансия', 'вакансии', 'вакансий')} с открытым приёмом откликов` : 'Сейчас приём откликов закрыт') : ' '}
          </p>
        </div>

        {showFilters ? (
          <div className="mt-10 space-y-3">
            <form role="search" onSubmit={submit} className="flex gap-2">
              <label htmlFor="careers-search" className="sr-only">Поиск вакансий</label>
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-5 top-1/2 size-5 -translate-y-1/2 text-ok-indigo/60" aria-hidden />
                <input id="careers-search" type="search" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск по вакансиям"
                  className="h-14 w-full rounded-full border border-ok-line bg-ok-paper pl-13 pr-5 text-base text-ok-ink outline-none placeholder:text-ok-muted focus-visible:border-ok-indigo focus-visible:bg-white" />
              </div>
              <button type="submit" className="h-14 shrink-0 rounded-full bg-ok-indigo px-6 text-base font-bold text-white transition-colors hover:bg-ok-indigo-soft sm:px-8">Найти</button>
            </form>
            <button type="button" onClick={() => setFiltersOpen((v) => !v)} aria-expanded={filtersOpen} aria-controls="careers-filters"
              className="inline-flex h-11 items-center gap-2 rounded-full border border-ok-line px-5 text-[15px] font-bold text-ok-indigo sm:hidden">
              <SlidersHorizontal className="size-4" aria-hidden />
              Фильтры{activeFilters ? ` · ${activeFilters}` : ''}
            </button>
            <div id="careers-filters" className={cn('gap-2 sm:grid sm:grid-cols-2 lg:grid-cols-5', filtersOpen ? 'grid' : 'hidden')}>
              <FilterSelect label="Направление" value={query.department} onChange={(v) => update({ department: v })} placeholder="Все направления"
                options={(filters.data?.departments ?? []).map((d) => ({ value: d, label: d }))} />
              <FilterSelect label="Формат работы" value={query.work_format} onChange={(v) => update({ work_format: v })} placeholder="Любой формат"
                options={filters.data?.work_formats ?? []} />
              <FilterSelect label="Тип занятости" value={query.employment_type} onChange={(v) => update({ employment_type: v })} placeholder="Любая занятость"
                options={filters.data?.employment_types ?? []} />
              <FilterSelect label="Город" value={query.location} onChange={(v) => update({ location: v })} placeholder="Все города"
                options={(filters.data?.locations ?? []).map((l) => ({ value: l, label: l }))} />
              <FilterSelect label="Сортировка" value={query.ordering || 'newest'} onChange={(v) => update({ ordering: v === 'newest' ? '' : v })} options={ORDERINGS}
                active={Boolean(query.ordering)} />
            </div>
            {hasFilters ? (
              <button type="button" onClick={reset} className="inline-flex items-center gap-1.5 text-[15px] font-semibold text-ok-indigo hover:underline">
                <X className="size-4" aria-hidden />Сбросить фильтры{query.search ? ` (поиск: «${query.search}»)` : ''}
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="mt-10 overflow-hidden rounded-[28px] border border-ok-line" aria-live="polite" aria-busy={list.isFetching}>
          {list.isPending ? (
            <div className="px-6 md:px-0"><VacancySkeleton /><VacancySkeleton /><VacancySkeleton /></div>
          ) : list.isError ? (
            <div className="flex flex-col items-center gap-4 px-6 py-16 text-center" role="alert">
              <span className="flex size-12 items-center justify-center rounded-full bg-danger-soft text-danger"><AlertTriangle className="size-5" aria-hidden /></span>
              <div>
                <p className="text-xl font-bold text-ok-ink">Не удалось загрузить вакансии</p>
                <p className="mt-1 text-ok-muted">{extractErrorMessage(list.error, 'Проверьте соединение и попробуйте ещё раз.')}</p>
              </div>
              <button type="button" onClick={() => void list.refetch()} className="h-11 rounded-full border-2 border-ok-indigo/20 px-6 font-bold text-ok-indigo hover:bg-ok-paper">Повторить</button>
            </div>
          ) : list.data.results.length === 0 ? (
            <div className="relative overflow-hidden bg-ok-indigo-50 px-6 py-16 sm:px-12">
              <div className="absolute -right-10 -top-6 w-72 opacity-20 sm:w-96" aria-hidden><GlassesMark stroke="var(--color-ok-indigo)" /></div>
              <div className="relative max-w-xl">
                <p className="text-2xl font-extrabold text-ok-indigo">{hasFilters ? 'По вашему запросу вакансий нет' : 'Открытых вакансий пока нет'}</p>
                <p className="mt-3 text-lg leading-relaxed text-ok-muted">
                  {hasFilters
                    ? 'Попробуйте изменить запрос или сбросить фильтры — возможно, подходящая вакансия называется иначе.'
                    : 'Новые вакансии появляются здесь сразу после публикации. Отклик принимается на конкретную вакансию — загляните сюда позже.'}
                </p>
                {hasFilters ? (
                  <button type="button" onClick={reset} className="mt-6 h-12 rounded-full bg-ok-indigo px-6 font-bold text-white hover:bg-ok-indigo-soft">Сбросить фильтры</button>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="px-6 md:px-0">
              {list.data.results.map((vacancy) => <VacancyCard key={vacancy.slug} vacancy={vacancy} />)}
            </div>
          )}
        </div>

        {list.data && pages > 1 ? (
          <nav className="mt-6 flex items-center justify-between gap-3" aria-label="Страницы вакансий">
            <p className="text-[15px] text-ok-muted">Страница {page} из {pages}</p>
            <div className="flex gap-2">
              <button type="button" disabled={page <= 1} onClick={() => goTo(page - 1)} aria-label="Предыдущая страница"
                className="flex size-11 items-center justify-center rounded-full border border-ok-line text-ok-indigo hover:bg-ok-paper disabled:opacity-40">
                <ChevronLeft className="size-5" aria-hidden />
              </button>
              <button type="button" disabled={page >= pages} onClick={() => goTo(page + 1)} aria-label="Следующая страница"
                className="flex size-11 items-center justify-center rounded-full border border-ok-line text-ok-indigo hover:bg-ok-paper disabled:opacity-40">
                <ChevronRight className="size-5" aria-hidden />
              </button>
            </div>
          </nav>
        ) : null}
      </div>
    </section>
  )
}
