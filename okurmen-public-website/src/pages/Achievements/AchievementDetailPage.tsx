import { Award, CalendarDays } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { AchievementCard } from '@/components/cards/AchievementCard'
import { ArticleLayout } from '@/components/layout/ArticleLayout'
import { CardGrid } from '@/components/sections/CardGrid'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { isNotFound, useAchievement } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { AchievementDetail } from '@/types/api'
import { excerpt } from '@/utils/format'

export function AchievementDetailPage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useAchievement(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <AchievementView item={data} />
}

export function AchievementView({ item, preview }: { item: AchievementDetail; preview?: boolean }) {
  const { t, formatDate } = useI18n()
  return (
    <>
      <Seo
        title={item.title}
        description={item.excerpt || excerpt(item.body)}
        image={item.cover?.url}
        type="article"
        noindex={preview}
        jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('achievements.title'), path: '/achievements' }, { name: item.title, path: `/achievements/${item.slug}` }])}
      />
      <ArticleLayout
        preview={preview}
        title={item.title}
        lead={item.excerpt}
        crumbs={[{ label: t('nav.achievements'), to: '/achievements' }, { label: item.title }]}
        meta={
          <>
            <span className="flex items-center gap-1.5"><Award className="size-4 text-gold-500" aria-hidden />{t(`achievements.cat.${item.category}`)}</span>
            <time dateTime={item.date} className="flex items-center gap-1.5"><CalendarDays className="size-4 text-brand-400" aria-hidden />{formatDate(item.date)}</time>
          </>
        }
        cover={item.cover}
        body={item.body}
        photos={item.photos}
        photosTitle={t('achievements.photos')}
        related={item.related.length ? (
          <section className="section bg-surface-soft">
            <div className="container-page">
              <SectionHeader title={t('achievements.related')} link={{ to: '/achievements', label: t('cta.allAchievements') }} />
              <CardGrid items={item.related} keyOf={(a) => a.slug} render={(a) => <AchievementCard item={a} />} />
            </div>
          </section>
        ) : null}
      />
    </>
  )
}
