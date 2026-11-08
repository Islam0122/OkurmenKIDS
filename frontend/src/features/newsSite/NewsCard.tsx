import { motion } from 'framer-motion'
import { ArrowRight, CalendarDays, Images } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { NewsCard as NewsCardData } from '@/api/publicNews'
import { cardVariants } from '@/features/portal/AppCard'
import { useI18n } from '@/features/portal/i18n'
import { cn } from '@/utils/cn'

import { formatNewsDate } from './format'
import { NewsImage } from './NewsImage'

export function CategoryBadge({ category, className }: { category: NewsCardData['category']; className?: string }) {
  const { t } = useI18n()
  return (
    <span className={cn('inline-flex items-center rounded-full bg-pd-green px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white', className)}>
      {t.news.categories[category]}
    </span>
  )
}

/** A news card: cover, category, date, title, excerpt, «Read More». */
export function NewsCard({ item }: { item: NewsCardData }) {
  const { t, lang } = useI18n()
  const n = t.news
  return (
    <motion.li variants={cardVariants} className="min-w-0 list-none">
      <Link
        to={`/news/${item.slug}`}
        className="group flex h-full flex-col overflow-hidden rounded-2xl border border-pd-line bg-pd-panel pd-shadow outline-none transition-[border-color,box-shadow,transform] duration-300 hover:-translate-y-1 hover:border-pd-green-line hover:pd-shadow-lg focus-visible:border-pd-green focus-visible:ring-4 focus-visible:ring-pd-green/15"
        data-news={item.slug}
      >
        <div className="relative aspect-[3/2] overflow-hidden bg-pd-subtle">
          <NewsImage image={item.cover} sizes="(min-width: 1024px) 360px, (min-width: 640px) 50vw, 100vw" className="transition-transform duration-500 group-hover:scale-[1.04]" />
          <CategoryBadge category={item.category} className="absolute left-3 top-3 shadow-sm" />
          {item.photo_count > 1 ? (
            <span className="absolute bottom-3 right-3 inline-flex items-center gap-1 rounded-full bg-zinc-950/60 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur">
              <Images className="size-3.5" aria-hidden />
              {n.photos(item.photo_count)}
            </span>
          ) : null}
        </div>
        <div className="flex flex-1 flex-col p-4 sm:p-5">
          <p className="inline-flex items-center gap-1 text-xs text-pd-faint">
            <CalendarDays className="size-3.5" aria-hidden />
            <time dateTime={item.published_at}>{formatNewsDate(item.published_at, lang)}</time>
          </p>
          <h3 className="mt-2 line-clamp-2 text-lg font-bold leading-snug tracking-tight">{item.title}</h3>
          {item.excerpt ? <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-pd-muted">{item.excerpt}</p> : null}
          <span className="mt-auto inline-flex items-center gap-1 pt-4 text-sm font-semibold text-pd-green transition-colors group-hover:text-pd-green-deep">
            {n.readMore}
            <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden />
          </span>
        </div>
      </Link>
    </motion.li>
  )
}

export function NewsCardSkeleton() {
  return (
    <li className="list-none overflow-hidden rounded-2xl border border-pd-line bg-pd-panel pd-shadow" aria-hidden>
      <div className="aspect-[3/2] animate-pulse bg-zinc-100" />
      <div className="space-y-3 p-5">
        <div className="h-3 w-24 animate-pulse rounded bg-zinc-100" />
        <div className="h-5 w-4/5 animate-pulse rounded bg-zinc-100" />
        <div className="h-3 w-full animate-pulse rounded bg-zinc-100" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-zinc-100" />
      </div>
    </li>
  )
}

/** The big story at the top of /news. */
export function FeaturedNews({ item }: { item: NewsCardData }) {
  const { t, lang } = useI18n()
  const n = t.news
  return (
    <motion.article initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
      <Link
        to={`/news/${item.slug}`}
        className="group grid overflow-hidden rounded-3xl border border-pd-line bg-pd-panel pd-shadow outline-none transition-[border-color,box-shadow] duration-300 hover:border-pd-green-line hover:pd-shadow-lg focus-visible:ring-4 focus-visible:ring-pd-green/15 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]"
        data-news={item.slug}
      >
        <div className="relative aspect-[16/10] overflow-hidden bg-pd-subtle lg:aspect-auto lg:min-h-[400px]">
          <NewsImage image={item.cover} sizes="(min-width: 1024px) 660px, 100vw" priority className="absolute inset-0 transition-transform duration-700 group-hover:scale-[1.03]" />
        </div>
        <div className="flex flex-col justify-center p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-pd-green-line bg-pd-green-soft px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-pd-green-deep">{n.featured}</span>
            <CategoryBadge category={item.category} />
          </div>
          <h2 className="mt-4 text-balance text-2xl font-extrabold leading-tight tracking-[-0.02em] sm:text-3xl">{item.title}</h2>
          {item.excerpt ? <p className="mt-3 line-clamp-4 text-pd-muted">{item.excerpt}</p> : null}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <span className="inline-flex items-center gap-1.5 text-sm text-pd-faint">
              <CalendarDays className="size-4" aria-hidden />
              <time dateTime={item.published_at}>{formatNewsDate(item.published_at, lang)}</time>
            </span>
            <span className="inline-flex h-10 items-center gap-2 rounded-lg bg-pd-green px-4 text-sm font-semibold text-white pd-shadow transition group-hover:bg-pd-green-deep">
              {n.readMore}
              <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden />
            </span>
          </div>
        </div>
      </Link>
    </motion.article>
  )
}
