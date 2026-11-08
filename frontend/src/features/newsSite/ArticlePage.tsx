import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { motion } from 'framer-motion'
import { AlertTriangle, ArrowLeft, CalendarDays, Images, SearchX, UserRound } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { publicNewsApi, type NewsArticle } from '@/api/publicNews'
import { useI18n } from '@/features/portal/i18n'
import { Lightbox, type LightboxImage } from '@/features/portal/Lightbox'
import { PortalShell } from '@/features/portal/PortalShell'
import { StatusBlock, buttonPrimary, buttonSecondary } from '@/features/projectsSite/StatusBlock'
import { resolveMediaUrl } from '@/lib/mediaUrl'

import { ArticleBody } from './ArticleBody'
import { formatNewsDate } from './format'
import { CategoryBadge, NewsCard } from './NewsCard'
import { NewsImage } from './NewsImage'
import { PhotoGallery } from './PhotoGallery'
import { ShareBar } from './ShareBar'

const backLink =
  'inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-pd-muted transition hover:text-pd-green focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-pd-green'

/** /news/:slug — one published article (no login). */
export function ArticlePage() {
  const { slug = '' } = useParams()
  const query = useQuery({
    queryKey: ['public-news-article', slug],
    queryFn: () => publicNewsApi.article(slug),
    retry: (count, error) => !(isAxiosError(error) && error.response?.status === 404) && count < 1,
  })
  return (
    <PortalShell title={(t) => query.data?.title ?? t.news.title} backHome>
      <Article query={query} />
    </PortalShell>
  )
}

function Article({ query }: { query: ReturnType<typeof useQuery<NewsArticle>> }) {
  const { t } = useI18n()
  const n = t.news
  const notFound = isAxiosError(query.error) && query.error.response?.status === 404

  return (
    <main className="mx-auto w-full max-w-[1100px] flex-1 px-4 pb-14 pt-4 sm:px-6 sm:pt-6">
      <Link to="/news" className={backLink}>
        <ArrowLeft className="size-4" aria-hidden /> {n.back}
      </Link>
      <div className="mt-5" aria-live="polite" aria-busy={query.isFetching}>
        {query.isPending ? (
          <ArticleSkeleton label={n.loading} />
        ) : notFound ? (
          <StatusBlock icon={SearchX} title={n.notFoundTitle} text={n.notFoundText}
            action={<Link to="/news" className={buttonSecondary}>{n.back}</Link>} />
        ) : query.isError ? (
          <StatusBlock icon={AlertTriangle} tone="danger" title={n.errorTitle} text={n.errorText}
            action={<button type="button" className={buttonPrimary} onClick={() => void query.refetch()}>{n.retry}</button>} />
        ) : (
          <ArticleView article={query.data} />
        )}
      </div>
    </main>
  )
}

function ArticleView({ article }: { article: NewsArticle }) {
  const { t, lang } = useI18n()
  const n = t.news
  const [viewer, setViewer] = useState<number | null>(null)

  // The lightbox walks through the cover and then every photo.
  const slides = useMemo<LightboxImage[]>(() => {
    const all = [...(article.cover ? [article.cover] : []), ...article.photos]
    return all.flatMap((image) => {
      const src = resolveMediaUrl(image.url)
      return src ? [{ src, caption: image.caption, width: image.width, height: image.height }] : []
    })
  }, [article])
  const offset = article.cover ? 1 : 0
  const photoCount = slides.length

  return (
    <motion.article initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <header className="mx-auto max-w-3xl text-center">
        <CategoryBadge category={article.category} />
        <h1 className="mt-4 text-balance text-3xl font-extrabold leading-[1.15] tracking-[-0.025em] sm:text-4xl lg:text-[2.75rem]">{article.title}</h1>
        {article.excerpt ? <p className="mx-auto mt-4 max-w-2xl text-pretty text-lg leading-relaxed text-pd-muted">{article.excerpt}</p> : null}
        <p className="mt-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 text-sm text-pd-faint">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays className="size-4" aria-hidden />
            <time dateTime={article.published_at}>{formatNewsDate(article.published_at, lang)}</time>
          </span>
          {article.author ? (
            <span className="inline-flex items-center gap-1.5">
              <UserRound className="size-4" aria-hidden />
              <span className="sr-only">{n.author}: </span>
              {article.author}
            </span>
          ) : null}
          {photoCount > 1 ? (
            <span className="inline-flex items-center gap-1.5">
              <Images className="size-4" aria-hidden />
              {n.photos(photoCount)}
            </span>
          ) : null}
        </p>
      </header>

      {article.cover ? (
        <figure className="mt-8">
          <button
            type="button"
            onClick={() => setViewer(0)}
            aria-label={n.open(1)}
            className="group block w-full overflow-hidden rounded-3xl border border-pd-line bg-pd-subtle pd-shadow outline-none focus-visible:ring-4 focus-visible:ring-pd-green/20"
            style={{ aspectRatio: article.cover.width && article.cover.height ? `${Math.max(article.cover.width / article.cover.height, 4 / 3)}` : '16 / 9' }}
          >
            <NewsImage image={article.cover} sizes="(min-width: 1100px) 1100px, 100vw" priority alt={article.cover.caption}
              className="transition-transform duration-700 group-hover:scale-[1.02]" />
          </button>
          {article.cover.caption ? <figcaption className="mt-3 text-center text-sm text-pd-muted">{article.cover.caption}</figcaption> : null}
        </figure>
      ) : null}

      {article.body ? (
        <div className="mx-auto mt-10 max-w-[68ch]">
          <ArticleBody body={article.body} />
        </div>
      ) : null}

      {article.photos.length > 0 ? (
        <section className="mt-12" aria-labelledby="news-gallery">
          <h2 id="news-gallery" className="mb-5 flex items-center gap-2 text-xl font-bold tracking-tight">
            <Images className="size-5 text-pd-green" aria-hidden />
            {n.gallery}
            <span className="text-base font-medium text-pd-faint">· {article.photos.length}</span>
          </h2>
          <PhotoGallery photos={article.photos} offset={offset} onOpen={setViewer} />
        </section>
      ) : null}

      <div className="mx-auto mt-10 max-w-[68ch] border-t border-pd-line pt-6">
        <ShareBar title={article.title} />
      </div>

      {article.related.length > 0 ? (
        <section className="mt-14" aria-labelledby="related-news">
          <h2 id="related-news" className="mb-5 text-xl font-bold tracking-tight">{n.related}</h2>
          <motion.ul initial="hidden" animate="show" variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }} className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {article.related.map((item) => (
              <NewsCard key={item.slug} item={{ ...item, photo_count: item.photo_count ?? 0 }} />
            ))}
          </motion.ul>
        </section>
      ) : null}

      <Lightbox images={slides} index={viewer} onIndex={setViewer} label={n.photo} prev={n.prev} next={n.next} />
    </motion.article>
  )
}

function ArticleSkeleton({ label }: { label: string }) {
  return (
    <div className="mx-auto max-w-3xl">
      <p className="sr-only">{label}</p>
      <div className="mx-auto h-5 w-32 animate-pulse rounded-full bg-zinc-100" />
      <div className="mx-auto mt-4 h-10 w-4/5 animate-pulse rounded bg-zinc-100" />
      <div className="mx-auto mt-3 h-5 w-2/3 animate-pulse rounded bg-zinc-100" />
      <div className="mt-8 aspect-[16/9] animate-pulse rounded-3xl bg-zinc-100" />
    </div>
  )
}
