import { AchievementCard } from '@/components/cards/AchievementCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useAchievements } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { AchievementCategory } from '@/types/api'

const CATEGORIES: AchievementCategory[] = ['competition', 'award', 'certificate', 'student', 'milestone', 'partnership', 'recognition']

export function AchievementsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['category'])
  const category = params.category || 'all'
  const { data, isPending, isError, error, refetch } = useAchievements({ category, page, page_size: 12 })
  const counts = data?.counts ?? {}
  const chips = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...CATEGORIES.map((c) => ({ value: c, label: t(`achievements.cat.${c}`), count: counts[c] })).filter((c) => c.count || c.value === category),
  ]
  return (
    <>
      <Seo title={t('achievements.title')} description={t('achievements.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('achievements.title'), path: '/achievements' }])} />
      <PageHero title={t('achievements.title')} text={t('achievements.subtitle')} crumbs={[{ label: t('nav.achievements') }]} />
      <section className="container-page section">
        {data && data.counts.all > 0 ? (
          <div className="mb-8"><FilterChips chips={chips} value={category} onChange={(v) => update({ category: v })} label={t('nav.achievements')} /></div>
        ) : null}
        {isPending ? <CardSkeletons count={6} aspect="aspect-[4/3]" /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : data.results.length ? (
          <>
            <CardGrid items={data.results} keyOf={(a) => a.slug} render={(a) => <AchievementCard item={a} />} />
            <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p })} />
          </>
        ) : <EmptyState search={category !== 'all'} />}
      </section>
    </>
  )
}
