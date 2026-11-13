import { ArrowLeft, CalendarDays, Tag, UserRound } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { AchievementImage, AchievementShowcaseCard } from '@/components/cards/AchievementShowcaseCard'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { crumbsLd, detailDescription, detailTitle, Seo } from '@/components/shared/Seo'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { Gallery } from '@/features/content/Gallery'
import { RichText } from '@/features/content/RichText'
import { ShareButton } from '@/features/content/ShareButton'
import { isNotFound, useAchievement } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { AchievementDetail } from '@/types/api'
import { cn } from '@/utils/cn'
import { useItemLangs } from '@/hooks/queries'

const CATALOG = 'mx-auto w-[calc(100%-48px)] max-w-[1280px]'

export function AchievementDetailPage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useAchievement(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <AchievementView item={data} />
}

/** Also used by /preview/<token> (draft from the LMS editor). */
export function AchievementView({ item, preview }: { item: AchievementDetail; preview?: boolean }) {
  const { t, path, formatDate, lang } = useI18n()
  const langs = useItemLangs('achievements', item.slug, preview ? undefined : item)
  const facts = [
    { icon: CalendarDays, label: t('achievements.date'), value: formatDate(item.date) },
    { icon: Tag, label: t('achievements.category'), value: t(`achievements.cat.${item.category}`) },
    item.recipient ? { icon: UserRound, label: t('achievements.recipient'), value: item.recipient } : null,
  ].filter(Boolean) as { icon: typeof Tag; label: string; value: string }[]

  return (
    <>
      <Seo
        title={detailTitle(lang, 'achievements', item.title, item.seo_title)}
        description={detailDescription(lang, 'achievements', item.excerpt || item.body, item.seo_description)}
        image={item.cover?.url}
        type="article"
        noindex={preview}
        langs={langs}
        jsonLd={crumbsLd(lang, 'achievements', { name: item.title, slug: item.slug })}
      />

      {/* Editorial header: the achievement image is the main visual */}
      <section className="relative overflow-hidden bg-surface-purple">
        <div aria-hidden className="pointer-events-none absolute -top-24 -right-24 size-80 rounded-full bg-gold-200/40 blur-3xl" />
        <div className={`${CATALOG} relative grid gap-8 py-8 sm:py-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-center lg:gap-12 lg:py-14`}>
          <div className="lg:order-2">
            <nav aria-label="breadcrumb" className="mb-4">
              <Link to={path('/achievements')} className="-ml-2 inline-flex min-h-10 items-center gap-1.5 rounded-full px-2 text-sm font-bold text-brand-700 hover:bg-white/70 hover:text-brand-900">
                <ArrowLeft className="size-4" aria-hidden /> {t('achievements.group.all')}
              </Link>
            </nav>
            <h1 className="text-page-title font-black">{item.title}</h1>
            {item.excerpt ? <p className="mt-4 text-base leading-relaxed text-ink-soft sm:text-lg">{item.excerpt}</p> : null}
            <dl className="mt-6 grid gap-3 sm:grid-cols-2">
              {facts.map((f) => (
                <div key={f.label} className="flex items-center gap-3 rounded-2xl bg-white/85 px-4 py-3 shadow-soft">
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><f.icon className="size-4" aria-hidden /></span>
                  <div className="min-w-0">
                    <dt className="text-xs font-bold tracking-wide text-muted uppercase">{f.label}</dt>
                    <dd className="font-bold break-words text-ink">{f.value}</dd>
                  </div>
                </div>
              ))}
            </dl>
            {!preview ? <div className="mt-6"><ShareButton title={item.title} /></div> : null}
          </div>
          <Reveal className="lg:order-1">
            <figure>
              <AchievementImage item={item} priority sizes="(min-width: 1024px) 55vw, 100vw"
                className="aspect-[4/3] rounded-[2rem] shadow-lift ring-8 ring-white" />
              {item.cover?.caption ? <figcaption className="mt-3 text-center text-sm text-muted">{item.cover.caption}</figcaption> : null}
            </figure>
          </Reveal>
        </div>
      </section>

      {/* Full story and additional photos */}
      {item.body || item.photos.length ? (
        <div className={`${CATALOG} py-10 sm:py-14`}>
          <article className="mx-auto max-w-3xl">
            <RichText source={item.body} />
            {item.photos.length ? (
              <section className={item.body ? 'mt-12' : ''}>
                <h2 className="mb-5 text-2xl font-black">{t('achievements.photos')}</h2>
                <Gallery photos={item.photos} title={item.title} />
              </section>
            ) : null}
          </article>
        </div>
      ) : null}

      {item.related.length ? (
        <section className="border-t border-line bg-surface-soft py-12 sm:py-14">
          <div className={CATALOG}>
            <SectionHeader title={t('achievements.related')} link={{ to: '/achievements', label: t('cta.allAchievements') }} />
            <ul className={cn('grid grid-cols-1 gap-6', item.related.length === 3 ? 'md:grid-cols-3' : 'sm:grid-cols-2 lg:grid-cols-3')}>
              {item.related.map((a) => <li key={a.slug} className="min-w-0"><AchievementShowcaseCard item={a} /></li>)}
            </ul>
          </div>
        </section>
      ) : null}
    </>
  )
}
