import { ProjectCard } from '@/components/cards/ProjectCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { SearchBox } from '@/components/shared/SearchBox'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useProjects } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { ProjectCategory } from '@/types/api'

const CATEGORIES: ProjectCategory[] = ['html-css', 'javascript', 'react', 'python', 'other']

export function ProjectsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['category', 'q'])
  const category = params.category || 'all'
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useProjects({ category, q: params.q, page, page_size: 12 })
  const counts = data?.counts ?? {}
  const chips = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...CATEGORIES.map((c) => ({ value: c, label: t(`projects.cat.${c}`), count: counts[c] })).filter((c) => c.count !== 0),
  ]
  return (
    <>
      <Seo title={t('projects.title')} description={t('projects.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('projects.title'), path: '/projects' }])} />
      <PageHero title={t('projects.title')} text={t('projects.subtitle')} crumbs={[{ label: t('nav.projects') }]} />
      <section className="container-page section">
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <FilterChips chips={chips} value={category} onChange={(v) => update({ category: v })} label={t('nav.projects')} />
          <SearchBox value={params.q} onChange={(q) => update({ q })} />
        </div>
        {isPending ? <CardSkeletons count={6} /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : data.results.length ? (
          <div className={isPlaceholderData ? 'opacity-60 transition' : 'transition'}>
            <CardGrid items={data.results} keyOf={(p) => p.key} render={(p) => <ProjectCard project={p} />} />
            <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p })} />
          </div>
        ) : <EmptyState search={Boolean(params.q || params.category)} />}
      </section>
    </>
  )
}
