import { Check, Code2, RotateCcw } from 'lucide-react'

import { ProjectCard } from '@/components/cards/ProjectCard'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { Reveal } from '@/components/shared/Reveal'
import { SearchBox } from '@/components/shared/SearchBox'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useProjects } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { ProjectCategory } from '@/types/api'
import { cn } from '@/utils/cn'

const CATEGORIES: ProjectCategory[] = ['html-css', 'javascript', 'react', 'python', 'other']
/** 12 fills complete rows at 1, 2, 3 and 4 columns. */
const PAGE_SIZE = 12
/** Wider than the standard page container: a gallery benefits from the space. */
const WIDE = 'mx-auto w-full max-w-[88rem] px-4 sm:px-6 lg:px-8'
/** Grid widths (gap 1.5rem): 1 / 2 / 3 / 4 per row; an incomplete last row is centred. */
const PROJECT_ITEM = 'w-full sm:w-[calc(50%-0.75rem)] lg:w-[calc(33.333%-1rem)] 2xl:w-[calc(25%-1.125rem)]'

interface Chip {
  value: string
  label: string
  count?: number
}

/** Accessible single-choice chips; scroll horizontally on phones. */
function ChipGroup({ label, chips, value, onChange, size = 'md' }: { label: string; chips: Chip[]; value: string; onChange: (v: string) => void; size?: 'md' | 'sm' }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 lg:flex-row lg:items-center lg:gap-4">
      <span className="shrink-0 text-xs font-bold tracking-wide text-muted uppercase lg:w-28">{label}</span>
      <div role="radiogroup" aria-label={label} className="-mx-4 flex min-w-0 snap-x gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
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
                'inline-flex shrink-0 snap-start items-center gap-1.5 rounded-full border font-bold transition duration-200 focus-visible:ring-4 focus-visible:ring-brand-100',
                size === 'md' ? 'h-10 px-4 text-sm' : 'h-8 px-3 text-xs',
                active
                  ? 'border-brand-800 bg-brand-800 text-white shadow-[0_6px_16px_-8px_rgb(41_19_109/0.6)]'
                  : 'border-line bg-white text-ink-soft hover:border-brand-300 hover:bg-brand-50/60 hover:text-brand-800',
              )}
            >
              {active && chip.value !== 'all' ? <Check className="size-3.5 text-gold-300" strokeWidth={3} aria-hidden /> : null}
              {chip.label}
              {chip.count !== undefined ? (
                <span className={cn('rounded-full px-1.5 tabular-nums', size === 'md' ? 'text-xs' : 'text-[10px]', active ? 'bg-white/20' : 'bg-surface-soft text-muted')}>{chip.count}</span>
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function ProjectsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['category', 'q', 'technology'])
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
  const techChips: Chip[] = [
    { value: 'all', label: t('filter.all') },
    ...techList.map((tech) => ({ value: tech.name, label: tech.name, count: tech.count })),
    // keep a selected technology visible even if it is not among the top ones
    ...(technology && !techList.some((x) => x.name.toLowerCase() === technology.toLowerCase()) ? [{ value: technology, label: technology }] : []),
  ]
  const activeTech = techChips.find((c) => c.value.toLowerCase() === technology.toLowerCase())?.value ?? 'all'
  const filtered = Boolean(params.q || params.category || technology)

  return (
    <>
      <Seo title={t('projects.title')} description={t('projects.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('projects.title'), path: '/projects' }])} />
      <PageHero compact wide title={t('projects.title')} text={t('projects.subtitle')} crumbs={[{ label: t('nav.projects') }]} />

      <section className={cn(WIDE, 'py-8 sm:py-10 lg:py-12')}>
        <div className="card mb-8 space-y-4 p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <SearchBox value={params.q} onChange={(q) => update({ q })} />
            <div className="flex items-center gap-3 text-sm">
              {data ? <span className="font-semibold text-muted" aria-live="polite">{t('projects.found', { count: data.count })}</span> : null}
              {filtered ? (
                <button type="button" onClick={() => update({ q: '', category: '', technology: '' })} className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 font-bold text-brand-700 hover:bg-brand-50">
                  <RotateCcw className="size-3.5" aria-hidden /> {t('projects.reset')}
                </button>
              ) : null}
            </div>
          </div>
          <ChipGroup label={t('projects.filter.category')} chips={categoryChips} value={category} onChange={(v) => update({ category: v, technology })} />
          {techList.length > 1 ? (
            <ChipGroup label={t('projects.filter.technology')} chips={techChips} value={activeTech} size="sm" onChange={(v) => update({ technology: v === 'all' ? '' : v, category })} />
          ) : null}
        </div>

        {isPending ? (
          <CardSkeletons count={8} className="lg:grid-cols-3 2xl:grid-cols-4" aspect="aspect-video" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : data.results.length ? (
          <div className={cn('transition-opacity', isPlaceholderData && 'opacity-60')}>
            <ul className="flex flex-wrap justify-center gap-6">
              {data.results.map((project, i) => (
                <Reveal as="li" key={project.key} delay={Math.min(i, 8) * 0.04} className={PROJECT_ITEM}>
                  <ProjectCard project={project} />
                </Reveal>
              ))}
            </ul>
            <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p, category: params.category, q: params.q, technology })} />
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
