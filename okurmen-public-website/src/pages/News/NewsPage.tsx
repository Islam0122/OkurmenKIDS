import { NewsCard } from '@/components/cards/NewsCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { Reveal } from '@/components/shared/Reveal'
import { SearchBox } from '@/components/shared/SearchBox'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useNews } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { NewsCategory } from '@/types/api'

const CATEGORIES: NewsCategory[] = ['events', 'achievements', 'competitions', 'education', 'announcements', 'activities']

export function NewsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['category', 'q'])
  const category = params.category || 'all'
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useNews({ category, q: params.q, page, page_size: 9 })
  const counts = data?.counts ?? {}
  const chips = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...CATEGORIES.map((c) => ({ value: c, label: t(`news.cat.${c}`), count: counts[c] })).filter((c) => c.count || c.value === category),
  ]
  return (
    <>
      <Seo title={t('news.title')} description={t('news.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('news.title'), path: '/news' }])} />
      <PageHero title={t('news.title')} text={t('news.subtitle')} crumbs={[{ label: t('nav.news') }]} />
      <section className="container-page section">
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <FilterChips chips={chips} value={category} onChange={(v) => update({ category: v })} label={t('nav.news')} />
          <SearchBox value={params.q} onChange={(q) => update({ q })} />
        </div>
        {isPending ? <CardSkeletons count={6} /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : (
          <div className={isPlaceholderData ? 'opacity-60 transition' : 'transition'}>
            {data.featured ? <Reveal className="mb-8"><NewsCard item={data.featured} featured /></Reveal> : null}
            {data.results.length ? (
              <>
                <CardGrid items={data.results} keyOf={(n) => n.slug} render={(n) => <NewsCard item={n} />} />
                <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p })} />
              </>
            ) : !data.featured ? <EmptyState search={Boolean(params.q || params.category)} /> : null}
          </div>
        )}
      </section>
    </>
  )
}
