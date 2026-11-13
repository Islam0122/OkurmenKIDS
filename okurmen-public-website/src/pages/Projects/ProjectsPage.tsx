import { Check, ChevronDown, Code2, RotateCcw } from 'lucide-react'
import { useId, useState } from 'react'

import { ProjectCard } from '@/components/cards/ProjectCard'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { Reveal } from '@/components/shared/Reveal'
import { SearchBox } from '@/components/shared/SearchBox'
import { crumbsLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useProjects } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { ProjectCategory } from '@/types/api'
import { cn } from '@/utils/cn'

const CATEGORIES: ProjectCategory[] = ['html-css', 'javascript', 'react', 'python', 'other']
/** 12 fills complete rows at 1, 2, 3 and 4 columns. */
const PAGE_SIZE = 12
/** Catalog container: width calc(100% - 48px), at most 1280px, centred (the hero uses the same). */
const CATALOG = 'mx-auto w-[calc(100%-48px)] max-w-[1280px]'
/** Technologies visible before «Ещё N». */
const TECH_VISIBLE = 10

interface Chip {
  value: string
  label: string
  count?: number
}

/** One filter row: a readable label above consistent, single-choice chips (scroll sideways on phones). */
function FilterRow({ label, chips, value, onChange, footer }: { label: string; chips: Chip[]; value: string; onChange: (v: string) => void; footer?: React.ReactNode }) {
  const id = useId()
  return (
    <div className="min-w-0">
      <p id={id} className="mb-2.5 text-sm font-bold text-ink">{label}</p>
      <div role="radiogroup" aria-labelledby={id}
        className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
        {chips.map((chip) => {
          const active = chip.value === value
          return (
            <button
              key={chip.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(active && chip.value !== 'all' ? 'all' : chip.value)}
              className={cn(
                'inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-sm font-semibold transition duration-200 focus-visible:ring-4 focus-visible:ring-brand-100',
                active
                  ? 'border-brand-800 bg-brand-800 text-white shadow-[0_6px_16px_-8px_rgb(41_19_109/0.6)]'
                  : 'border-line bg-white text-ink-soft hover:border-brand-300 hover:bg-brand-50/60 hover:text-brand-800',
              )}
            >
              {active && chip.value !== 'all' ? <Check className="size-3.5 text-gold-300" strokeWidth={3} aria-hidden /> : null}
              {chip.label}
              {chip.count !== undefined ? (
                <span className={cn('min-w-5 rounded-full px-1.5 text-center text-xs tabular-nums', active ? 'bg-white/20' : 'bg-surface-soft text-muted')}>{chip.count}</span>
              ) : null}
            </button>
          )
        })}
        {footer}
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const { t, lang } = useI18n()
  const { params, page, update } = useListParams(['category', 'q', 'technology'])
  const [allTech, setAllTech] = useState(false)
  const category = params.category || 'all'
  const technology = params.technology || ''
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useProjects({
    category, q: params.q, technology: technology || undefined, page, page_size: PAGE_SIZE,
  })

  const counts = data?.counts ?? {}
  const categoryChips: Chip[] = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...CATEGORIES.map((c) => ({ value: c, label: t(`projects.cat.${c}`), count: counts[c] })).filter((c) => c.count || c.value === category),
  ]
  const techList = data?.technologies ?? []
  const selectedTech = techList.find((x) => x.name.toLowerCase() === technology.toLowerCase())?.name ?? technology
  const techAll: Chip[] = [
    ...techList.map((tech) => ({ value: tech.name, label: tech.name, count: tech.count })),
    // a selected technology stays visible even when it is not among the listed ones
    ...(technology && !techList.some((x) => x.name.toLowerCase() === technology.toLowerCase()) ? [{ value: technology, label: technology }] : []),
  ]
  const hidden = Math.max(0, techAll.length - TECH_VISIBLE)
  const techShown = allTech ? techAll : techAll.filter((c, i) => i < TECH_VISIBLE || c.value === selectedTech)
  const techChips: Chip[] = [{ value: 'all', label: t('filter.all') }, ...techShown]
  const filtered = Boolean(params.q || params.category || technology)
  const results = data?.results ?? []

  return (
    <>
      <Seo page="/projects" jsonLd={crumbsLd(lang, 'projects')} />
      <PageHero compact wide title={t('projects.title')} text={t('projects.subtitle')} crumbs={[{ label: t('nav.projects') }]} />

      <section className={cn(CATALOG, 'pt-8 pb-14 sm:pt-10 sm:pb-16')}>
        {/* Filters */}
        <div className="card mb-8 overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-line bg-surface-soft/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div className="w-full sm:max-w-md"><SearchBox value={params.q} onChange={(q) => update({ q })} /></div>
            <div className="flex items-center justify-between gap-3 sm:justify-end">
              {data ? (
                <span className="rounded-full bg-white px-3.5 py-1.5 text-sm font-bold text-brand-800 shadow-soft" aria-live="polite">
                  {t('projects.found', { count: data.count })}
                </span>
              ) : null}
              {filtered ? (
                <button type="button" onClick={() => update({ q: '', category: '', technology: '' })}
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-bold text-brand-700 hover:bg-brand-50">
                  <RotateCcw className="size-3.5" aria-hidden /> {t('projects.reset')}
                </button>
              ) : null}
            </div>
          </div>
          <div className="space-y-5 px-5 py-5 sm:px-6">
            <FilterRow label={t('projects.filter.category')} chips={categoryChips} value={category} onChange={(v) => update({ category: v })} />
            {techList.length > 1 ? (
              <FilterRow
                label={t('projects.filter.technology')}
                chips={techChips}
                value={technology ? selectedTech : 'all'}
                onChange={(v) => update({ technology: v === 'all' ? '' : v })}
                footer={hidden > 0 ? (
                  <button type="button" onClick={() => setAllTech((v) => !v)} aria-expanded={allTech}
                    className="inline-flex h-10 shrink-0 items-center gap-1 rounded-full px-3 text-sm font-bold text-brand-700 hover:bg-brand-50">
                    {allTech ? t('projects.lessTech') : t('projects.moreTech', { count: hidden })}
                    <ChevronDown className={cn('size-4 transition', allTech && 'rotate-180')} aria-hidden />
                  </button>
                ) : null}
              />
            ) : null}
          </div>
        </div>

        {/* Catalog: start-aligned grid, equal columns, 24px gaps */}
        {isPending ? (
          <CardSkeletons count={8} className="gap-6 lg:grid-cols-3 2xl:grid-cols-4" aspect="aspect-video" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : results.length ? (
          <div className={cn('transition-opacity', isPlaceholderData && 'opacity-60')}>
            <ul className={cn('grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3', results.length >= 4 && '2xl:grid-cols-4')}>
              {results.map((project, i) => (
                <Reveal as="li" key={project.key} delay={Math.min(i, 8) * 0.04} className="min-w-0">
                  <ProjectCard project={project} priority={i === 0} />
                </Reveal>
              ))}
            </ul>
            <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p })} />
          </div>
        ) : filtered ? (
          <EmptyState search />
        ) : (
          <div className="mx-auto flex max-w-xl flex-col items-center gap-3 rounded-3xl border border-line bg-surface-soft px-6 py-10 text-center">
            <Code2 className="size-9 text-brand-300" aria-hidden />
            <p className="text-muted">{t('state.empty')}</p>
          </div>
        )}
      </section>
    </>
  )
}
