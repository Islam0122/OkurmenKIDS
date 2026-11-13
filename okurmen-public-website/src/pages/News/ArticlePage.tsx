import { CalendarDays, Tag, UserRound } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { NewsCard } from '@/components/cards/NewsCard'
import { ArticleLayout } from '@/components/layout/ArticleLayout'
import { CardGrid } from '@/components/sections/CardGrid'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { crumbsLd, detailDescription, detailTitle, Seo } from '@/components/shared/Seo'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { isNotFound, useArticle } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { NewsArticle } from '@/types/api'
import { absoluteUrl, mediaUrl } from '@/utils/media'
import { BRAND } from '@/app/config/site'
import { LOGO, plainText, type Lang } from '@/seo/core'

/** News is written in Russian only (apps.academy_news has no translations). */
const NEWS_LANGS: Lang[] = ['ru']

export function ArticlePage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useArticle(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <ArticleView article={data} />
}

export function ArticleView({ article, preview }: { article: NewsArticle; preview?: boolean }) {
  const { t, formatDate, lang } = useI18n()
  const description = detailDescription(lang, 'news', article.excerpt || article.body, article.seo_description)
  return (
    <>
      <Seo
        title={detailTitle(lang, 'news', article.title, article.seo_title)}
        description={description}
        image={article.cover?.url}
        type="article"
        publishedAt={article.published_at}
        noindex={preview}
        langs={NEWS_LANGS}
        jsonLd={[
          crumbsLd(lang, 'news', { name: article.title, slug: article.slug }),
          {
            '@context': 'https://schema.org',
            '@type': 'NewsArticle',
            headline: plainText(article.title).slice(0, 110),
            description,
            datePublished: article.published_at,
            ...(article.updated_at ? { dateModified: article.updated_at } : {}),
            inLanguage: 'ru',
            // News is written in Russian only: the canonical is always the Russian URL.
            mainEntityOfPage: { '@type': 'WebPage', '@id': absoluteUrl(`/news/${article.slug}`) },
            ...(article.cover ? { image: [absoluteUrl(mediaUrl(article.cover.url) ?? '')] } : {}),
            author: article.author ? { '@type': 'Person', name: article.author } : { '@type': 'Organization', '@id': absoluteUrl('/#organization'), name: BRAND.name, url: absoluteUrl('/') },
            publisher: { '@type': 'Organization', '@id': absoluteUrl('/#organization'), name: BRAND.name, logo: { '@type': 'ImageObject', url: absoluteUrl(LOGO.path), width: LOGO.width, height: LOGO.height } },
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
