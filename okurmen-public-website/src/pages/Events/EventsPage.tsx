import { ArrowRight, CalendarDays, CalendarHeart, Code2, Sparkles, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { EventCard } from '@/components/cards/EventCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { ButtonLink } from '@/components/shared/Button'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { Reveal } from '@/components/shared/Reveal'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useEvents } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { EventCard as Event, EventPhase } from '@/types/api'

const PHASES: EventPhase[] = ['upcoming', 'ongoing', 'completed']
/** The overview loads all published events at once (API maximum) and splits them by phase. */
const OVERVIEW_SIZE = 36
/** Past events shown in the overview; the rest behind «Бардыгы» (?phase=completed). */
const PAST_PREVIEW = 6

function EventsGrid({ events }: { events: Event[] }) {
  return <CardGrid items={events} keyOf={(e) => e.slug} render={(e) => <EventCard event={e} withDetails />} />
}

function SectionTitle({ title, count, link }: { title: string; count: number; link?: { to: string; label: string } }) {
  const { path } = useI18n()
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 sm:mb-8">
      <h2 className="flex items-center gap-3 text-2xl font-black sm:text-3xl">
        {title}
        {count ? <span className="rounded-full bg-brand-50 px-2.5 py-0.5 font-sans text-sm font-bold text-brand-600 tabular-nums">{count}</span> : null}
      </h2>
      {link ? (
        <Link to={path(link.to)} className="inline-flex min-h-11 items-center gap-1.5 font-bold text-brand-700 hover:text-brand-900">
          {link.label} <ArrowRight className="size-4" aria-hidden />
        </Link>
      ) : null}
    </div>
  )
}

export function EventsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['phase'])
  const phase = params.phase || 'all'
  const overview = phase === 'all'
  const { data, isPending, isError, error, refetch } = useEvents(overview ? { page_size: OVERVIEW_SIZE } : { phase, page, page_size: 9 })
  const counts = data?.counts ?? {}
  const total = counts.all ?? 0
  const chips = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...PHASES.map((p) => ({ value: p, label: t(`events.phase.${p}`), count: counts[p] })).filter((c) => c.count || c.value === phase),
  ]
  const results = data?.results ?? []
  const active = results.filter((e) => e.phase !== 'completed')
  const past = results.filter((e) => e.phase === 'completed')

  return (
    <>
      <Seo title={t('events.title')} description={t('events.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('events.title'), path: '/events' }])} />
      <PageHero compact title={t('events.heroTitle')} text={t('events.subtitle')} crumbs={[{ label: t('nav.events') }]} />

      <section className="container-page py-10 sm:py-12 lg:py-14">
        {isPending ? (
          <CardSkeletons count={3} />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : total === 0 ? (
          <EventsEmpty />
        ) : (
          <>
            <div className="mb-8 sm:mb-10"><FilterChips chips={chips} value={phase} onChange={(v) => update({ phase: v })} label={t('nav.events')} /></div>
            {overview ? (
              <div className="space-y-12 sm:space-y-14">
                <section aria-label={t('events.upcomingTitle')}>
                  <SectionTitle title={t('events.upcomingTitle')} count={active.length} />
                  {active.length ? (
                    <EventsGrid events={active} />
                  ) : (
                    <p className="flex items-center gap-3 rounded-2xl border border-dashed border-brand-200 bg-surface-purple/60 px-5 py-4 text-ink-soft">
                      <CalendarHeart className="size-5 shrink-0 text-brand-500" aria-hidden />
                      {t('events.noUpcoming')}
                    </p>
                  )}
                </section>
                {past.length ? (
                  <section aria-label={t('events.pastTitle')} className="border-t border-line pt-10 sm:pt-12">
                    <SectionTitle
                      title={t('events.pastTitle')}
                      count={counts.completed ?? past.length}
                      link={(counts.completed ?? 0) > PAST_PREVIEW ? { to: '/events?phase=completed', label: t('filter.all') } : undefined}
                    />
                    <EventsGrid events={past.slice(0, PAST_PREVIEW)} />
                  </section>
                ) : null}
              </div>
            ) : results.length ? (
              <>
                <EventsGrid events={results} />
                <Pagination page={data!.page} total={data!.num_pages} onChange={(p) => update({ page: p })} />
              </>
            ) : (
              <EmptyState search />
            )}
          </>
        )}
      </section>
    </>
  )
}

/** No published events at all: an intentional, friendly state (not an error). */
function EventsEmpty() {
  const { t } = useI18n()
  return (
    <Reveal className="mx-auto max-w-2xl">
      <div className="relative overflow-hidden rounded-[2rem] border border-brand-100 bg-gradient-to-b from-surface-purple/70 to-white px-6 py-10 text-center sm:px-12 sm:py-14">
        <div aria-hidden className="pointer-events-none absolute -top-16 -right-16 size-48 rounded-full bg-gold-200/40 blur-3xl" />
        <div aria-hidden className="relative mx-auto mb-7 h-28 w-40">
          <span className="absolute inset-x-6 inset-y-0 grid place-items-center rounded-3xl bg-white shadow-lift ring-1 ring-brand-100">
            <CalendarDays className="size-12 text-brand-600" strokeWidth={1.5} />
          </span>
          <span className="absolute top-1 -left-1 grid size-10 place-items-center rounded-2xl bg-gold-400 text-brand-900 shadow-gold motion-safe:animate-float">
            <Sparkles className="size-5" />
          </span>
          <span className="absolute -right-1 bottom-2 grid size-10 place-items-center rounded-2xl bg-brand-800 text-white shadow-soft">
            <Code2 className="size-5" />
          </span>
          <span className="absolute -bottom-2 left-3 grid size-8 place-items-center rounded-xl bg-white text-brand-500 shadow-soft ring-1 ring-brand-100">
            <Users className="size-4" />
          </span>
        </div>
        <h2 className="relative text-2xl font-black sm:text-3xl">{t('events.empty.title')}</h2>
        <p className="relative mx-auto mt-3 max-w-lg text-base leading-relaxed text-ink-soft sm:text-lg">{t('events.empty.text')}</p>
        <div className="relative mt-7 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink to="/courses">{t('cta.courses')}</ButtonLink>
          <ButtonLink to="/news" variant="outline">{t('nav.news')}</ButtonLink>
        </div>
      </div>
    </Reveal>
  )
}
