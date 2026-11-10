import { EventCard } from '@/components/cards/EventCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useEvents } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { EventPhase } from '@/types/api'

const PHASES: EventPhase[] = ['upcoming', 'ongoing', 'completed']

export function EventsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['phase'])
  const phase = params.phase || 'all'
  const { data, isPending, isError, error, refetch } = useEvents({ phase, page, page_size: 9 })
  const counts = data?.counts ?? {}
  const chips = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...PHASES.map((p) => ({ value: p, label: t(`events.phase.${p}`), count: counts[p] })).filter((c) => c.count || c.value === phase),
  ]
  return (
    <>
      <Seo title={t('events.title')} description={t('events.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('events.title'), path: '/events' }])} />
      <PageHero title={t('events.title')} text={t('events.subtitle')} crumbs={[{ label: t('nav.events') }]} />
      <section className="container-page section">
        {data && data.counts.all > 0 ? (
          <div className="mb-8"><FilterChips chips={chips} value={phase} onChange={(v) => update({ phase: v })} label={t('nav.events')} /></div>
        ) : null}
        {isPending ? <CardSkeletons count={6} /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : data.results.length ? (
          <>
            <CardGrid items={data.results} keyOf={(e) => e.slug} render={(e) => <EventCard event={e} />} />
            <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p })} />
          </>
        ) : <EmptyState search={phase !== 'all'} />}
      </section>
    </>
  )
}
