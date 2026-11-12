import { CalendarDays, Tag, UserRound } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { NewsCard } from '@/components/cards/NewsCard'
import { ArticleLayout } from '@/components/layout/ArticleLayout'
import { CardGrid } from '@/components/sections/CardGrid'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { isNotFound, useArticle } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { NewsArticle } from '@/types/api'
import { excerpt } from '@/utils/format'
import { absoluteUrl, mediaUrl } from '@/utils/media'

export function ArticlePage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useArticle(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <ArticleView article={data} />
}

export function ArticleView({ article, preview }: { article: NewsArticle; preview?: boolean }) {
  const { t, path, formatDate } = useI18n()
  return (
    <>
      <Seo
        title={article.seo_title || article.title}
        description={article.seo_description || article.excerpt || excerpt(article.body)}
        image={article.cover?.url}
        type="article"
        publishedAt={article.published_at}
        noindex={preview}
        jsonLd={[
          breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('news.title'), path: '/news' }, { name: article.title, path: `/news/${article.slug}` }]),
          {
            '@context': 'https://schema.org',
            '@type': 'NewsArticle',
            headline: article.title,
            description: article.excerpt,
            datePublished: article.published_at,
            mainEntityOfPage: absoluteUrl(path(`/news/${article.slug}`)),
            ...(article.cover ? { image: [absoluteUrl(mediaUrl(article.cover.url) ?? '')] } : {}),
            author: article.author ? { '@type': 'Person', name: article.author } : { '@type': 'Organization', name: 'Okurmen Kids Digital' },
            publisher: { '@type': 'Organization', name: 'Okurmen Kids Digital', logo: { '@type': 'ImageObject', url: absoluteUrl('/logo.png') } },
          },
        ]}
      />
      <ArticleLayout
        preview={preview}
        title={article.title}
        lead={article.excerpt}
        crumbs={[{ label: t('nav.news'), to: '/news' }, { label: article.title }]}
        meta={
          <>
            <span className="flex items-center gap-1.5"><Tag className="size-4 text-gold-500" aria-hidden />{t(`news.cat.${article.category}`)}</span>
            <time dateTime={article.published_at} className="flex items-center gap-1.5"><CalendarDays className="size-4 text-brand-400" aria-hidden />{formatDate(article.published_at)}</time>
            {article.author ? <span className="flex items-center gap-1.5"><UserRound className="size-4 text-brand-400" aria-hidden />{article.author}</span> : null}
          </>
        }
        cover={article.cover}
        body={article.body}
        photos={article.photos}
        photosTitle={t('news.photos')}
        related={article.related.length ? (
          <section className="section bg-surface-soft">
            <div className="container-page">
              <SectionHeader title={t('news.related')} link={{ to: '/news', label: t('cta.allNews') }} />
              <CardGrid items={article.related} keyOf={(n) => n.slug} render={(n) => <NewsCard item={n} />} />
            </div>
          </section>
        ) : null}
      />
    </>
  )
}
