import { ArrowRight, Images } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/shared/Badge'
import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { NewsCard as News } from '@/types/api'
import { cn } from '@/utils/cn'

export function NewsCard({ item, featured, readMore }: { item: News; featured?: boolean; /** homepage: a «read» arrow under the text */ readMore?: string }) {
  const { t, path, formatDate } = useI18n()
  return (
    <Link to={path(`/news/${item.slug}`)} className={cn('card card-hover group flex h-full overflow-hidden', featured ? 'flex-col lg:flex-row' : 'flex-col')}>
      <div className={cn('relative overflow-hidden bg-brand-50', featured ? 'aspect-[16/10] lg:aspect-auto lg:w-3/5' : 'aspect-[16/10]')}>
        <SmartImage image={item.cover} alt={item.title} sizes={featured ? '(min-width: 1024px) 60vw, 100vw' : undefined} className="size-full transition duration-700 group-hover:scale-105" />
        <Badge tone="white" className="absolute top-4 left-4">{t(`news.cat.${item.category}`)}</Badge>
      </div>
      <div className={cn('flex flex-1 flex-col', featured ? 'p-6 sm:p-8 lg:p-10' : 'p-6')}>
        {featured ? <span className="eyebrow mb-4 self-start">{t('news.featured')}</span> : null}
        <time dateTime={item.published_at} className="text-sm font-semibold text-muted">{formatDate(item.published_at)}</time>
        <h3 className={cn('mt-2 font-extrabold', featured ? 'text-2xl leading-tight sm:text-3xl' : 'text-lg leading-snug')}>{item.title}</h3>
        {item.excerpt ? <p className={cn('mt-3 text-muted', featured ? 'line-clamp-4' : 'line-clamp-3 text-[15px]')}>{item.excerpt}</p> : null}
        {readMore ? (
          <span className="mt-auto flex items-center justify-between gap-2 pt-4 text-sm font-bold text-brand-700">
            {readMore}
            <ArrowRight className="size-4 transition group-hover:translate-x-1" aria-hidden />
          </span>
        ) : item.photo_count > 1 ? (
          <span className="mt-auto flex items-center gap-1.5 pt-4 text-xs font-semibold text-muted"><Images className="size-4" aria-hidden />{item.photo_count}</span>
        ) : null}
      </div>
    </Link>
  )
}
