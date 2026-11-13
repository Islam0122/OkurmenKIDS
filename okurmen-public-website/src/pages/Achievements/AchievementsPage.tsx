import { Award, Handshake, Medal, Sparkles, Trophy } from 'lucide-react'

import { AchievementShowcaseCard } from '@/components/cards/AchievementShowcaseCard'
import { ButtonLink } from '@/components/shared/Button'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { Reveal } from '@/components/shared/Reveal'
import { crumbsLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useAchievements } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n, type MessageKey } from '@/i18n'
import type { AchievementCategory } from '@/types/api'
import { cn } from '@/utils/cn'

/** The page's filters group the API categories (achievements.cat.*). */
const GROUPS: Record<'students' | 'awards' | 'partnerships' | 'academy', AchievementCategory[]> = {
  students: ['competition', 'student'],
  awards: ['award', 'certificate', 'recognition'],
  partnerships: ['partnership'],
  academy: ['milestone'],
}
type Group = keyof typeof GROUPS
const PAGE_SIZE = 12
/** Wide screens: 4 columns only when that leaves a fuller last row than 3 (8 → 4+4, 6 → 3+3, 7 → 4+3). */
const fourColumns = (n: number) => n >= 4 && (n % 4 === 0 || (n % 3 !== 0 && n % 4 === 3))
/** Same width as the other gallery pages (hero + catalog). */
const CATALOG = 'mx-auto w-[calc(100%-48px)] max-w-[1280px]'

export function AchievementsPage() {
  const { t, lang } = useI18n()
  const { params, page, update } = useListParams(['group'])
  const group = (params.group in GROUPS ? params.group : 'all') as Group | 'all'
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useAchievements({
    category: group === 'all' ? undefined : GROUPS[group].join(','),
    page,
    page_size: PAGE_SIZE,
  })
  const counts = data?.counts ?? {}
  const total = counts.all ?? 0
  const sum = (g: Group) => GROUPS[g].reduce((n, c) => n + (counts[c] ?? 0), 0)
  const chips = [
    { value: 'all', label: t('achievements.group.all'), count: counts.all },
    ...(Object.keys(GROUPS) as Group[]).map((g) => ({ value: g, label: t(`achievements.group.${g}` as MessageKey), count: sum(g) })).filter((c) => c.count || c.value === group),
  ]
  const results = data?.results ?? []
  // Editorial highlight: on the first unfiltered page, the featured (or newest) achievement.
  const highlight = group === 'all' && page === 1 && results.length > 1 ? (results.find((a) => a.is_featured) ?? results[0]) : null
  const rest = highlight ? results.filter((a) => a.slug !== highlight.slug) : results

  return (
    <>
      <Seo page="/achievements" jsonLd={crumbsLd(lang, 'achievements')} />
      <PageHero compact wide title={t('achievements.heroTitle')} text={t('achievements.subtitle')} crumbs={[{ label: t('nav.achievements') }]} />

      <section className={cn(CATALOG, 'py-10 sm:py-12 lg:py-14')}>
        {isPending ? (
          <CardSkeletons count={3} aspect="aspect-[4/3]" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : total === 0 ? (
          <AchievementsEmpty />
        ) : (
          <>
            {chips.length > 2 ? (
              <div className="mb-8 sm:mb-10"><FilterChips chips={chips} value={group} onChange={(v) => update({ group: v })} label={t('nav.achievements')} /></div>
            ) : null}
            {results.length ? (
              <div className={cn('space-y-8 transition-opacity sm:space-y-10', isPlaceholderData && 'opacity-60')}>
                {highlight ? <Reveal><AchievementShowcaseCard item={highlight} highlight /></Reveal> : null}
                {rest.length ? (
                  <ul className={cn('grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3', fourColumns(rest.length) && '2xl:grid-cols-4')}>
                    {rest.map((item, i) => (
                      <Reveal as="li" key={item.slug} delay={Math.min(i, 6) * 0.05} className="min-w-0">
                        <AchievementShowcaseCard item={item} />
                      </Reveal>
                    ))}
                  </ul>
                ) : null}
                <Pagination page={data!.page} total={data!.num_pages} onChange={(p) => update({ page: p })} />
              </div>
            ) : (
              <EmptyState search />
            )}
          </>
        )}
      </section>
    </>
  )
}

/** Nothing published yet: an intentional, encouraging state. */
function AchievementsEmpty() {
  const { t } = useI18n()
  return (
    <Reveal className="mx-auto max-w-2xl">
      <div className="relative overflow-hidden rounded-[2rem] border border-brand-100 bg-gradient-to-b from-surface-purple/70 to-white px-6 py-10 text-center sm:px-12 sm:py-14">
        <div aria-hidden className="pointer-events-none absolute -top-16 -left-16 size-48 rounded-full bg-gold-200/40 blur-3xl" />
        <div aria-hidden className="relative mx-auto mb-7 h-28 w-40">
          <span className="absolute inset-x-6 inset-y-0 grid place-items-center rounded-3xl bg-white shadow-lift ring-1 ring-brand-100">
            <Trophy className="size-12 text-gold-500" strokeWidth={1.5} />
          </span>
          <span className="absolute top-1 -left-1 grid size-10 place-items-center rounded-2xl bg-brand-800 text-white shadow-soft motion-safe:animate-float">
            <Medal className="size-5" />
          </span>
          <span className="absolute -right-1 bottom-2 grid size-10 place-items-center rounded-2xl bg-gold-400 text-brand-900 shadow-gold">
            <Award className="size-5" />
          </span>
          <span className="absolute -bottom-2 left-3 grid size-8 place-items-center rounded-xl bg-white text-brand-500 shadow-soft ring-1 ring-brand-100">
            <Handshake className="size-4" />
          </span>
          <Sparkles className="absolute -top-2 right-2 size-5 text-gold-400" />
        </div>
        <h2 className="relative text-2xl font-black sm:text-3xl">{t('achievements.empty.title')}</h2>
        <p className="relative mx-auto mt-3 max-w-lg text-base leading-relaxed text-ink-soft sm:text-lg">{t('achievements.empty.text')}</p>
        <div className="relative mt-7 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink to="/projects">{t('nav.projects')}</ButtonLink>
          <ButtonLink to="/courses" variant="outline">{t('cta.courses')}</ButtonLink>
        </div>
      </div>
    </Reveal>
  )
}
