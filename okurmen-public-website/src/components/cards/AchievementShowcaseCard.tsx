import { ArrowRight, Award, CalendarDays, Images, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { AchievementCard as Achievement } from '@/types/api'
import { cn } from '@/utils/cn'

/** Certificates and diplomas are documents: show them whole instead of cropping. */
export const isDocument = (category: Achievement['category']) => category === 'certificate'

/** The achievement image: the main visual of the card; a calm award mark when there is none. */
export function AchievementImage({ item, className, sizes, priority }: { item: Achievement; className?: string; sizes?: string; priority?: boolean }) {
  const doc = isDocument(item.category)
  return (
    <div className={cn('relative overflow-hidden bg-gradient-to-br from-surface-purple via-white to-gold-50', className)}>
      <SmartImage
        image={item.cover}
        alt={item.cover?.caption || item.title}
        priority={priority}
        sizes={sizes}
        className={cn('size-full transition duration-700 ease-out group-hover:scale-[1.03]', doc ? 'object-contain! bg-transparent! p-4 drop-shadow-md sm:p-6' : 'object-cover')}
        fallback={<Award className="size-14 text-gold-500" strokeWidth={1.4} aria-hidden />}
      />
    </div>
  )
}

/**
 * Achievement card of the /achievements showcase (the homepage keeps its own
 * compact AchievementCard). `highlight` = the wide editorial card at the top.
 */
export function AchievementShowcaseCard({ item, highlight }: { item: Achievement; highlight?: boolean }) {
  const { t, path, formatDate } = useI18n()
  return (
    <Link
      to={path(`/achievements/${item.slug}`)}
      className={cn(
        'card group flex h-full overflow-hidden bg-white transition duration-300 hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift focus-visible:-translate-y-1',
        highlight ? 'flex-col lg:flex-row' : 'flex-col',
      )}
    >
      <div className={cn('relative', highlight ? 'lg:w-[56%] lg:shrink-0' : '')}>
        <AchievementImage item={item} className={cn(highlight ? 'aspect-[16/10] lg:aspect-auto lg:h-full lg:min-h-[22rem]' : 'aspect-[4/3]')}
          sizes={highlight ? '(min-width: 1024px) 56vw, 100vw' : '(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw'} priority={highlight} />
        <span className="absolute top-3 left-3 rounded-full bg-white/95 px-2.5 py-1 text-xs font-bold text-brand-800 shadow-soft backdrop-blur">
          {t(`achievements.cat.${item.category}`)}
        </span>
        {item.photo_count > 1 ? (
          <span className="absolute right-3 bottom-3 inline-flex items-center gap-1 rounded-full bg-brand-950/70 px-2 py-1 text-xs font-bold text-white backdrop-blur">
            <Images className="size-3.5" aria-hidden />{item.photo_count}
          </span>
        ) : null}
      </div>
      <div className={cn('flex flex-1 flex-col', highlight ? 'p-6 sm:p-8 lg:justify-center lg:p-10' : 'p-5 sm:p-6')}>
        {highlight ? <span className="eyebrow mb-4 self-start">{t('achievements.highlight')}</span> : null}
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-semibold text-gold-600">
          <span className="inline-flex items-center gap-1.5"><CalendarDays className="size-4" aria-hidden /><time dateTime={item.date}>{formatDate(item.date)}</time></span>
        </p>
        <h3 className={cn('mt-2 font-extrabold tracking-tight text-ink', highlight ? 'text-2xl leading-tight sm:text-3xl' : 'line-clamp-3 text-lg leading-snug')}>{item.title}</h3>
        {item.recipient ? (
          <p className="mt-2 inline-flex items-center gap-1.5 text-sm font-bold text-brand-600"><UserRound className="size-4 shrink-0" aria-hidden />{item.recipient}</p>
        ) : null}
        {item.excerpt ? (
          <p className={cn('mt-3 text-muted', highlight ? 'line-clamp-4 text-base leading-relaxed' : 'line-clamp-2 text-[15px] leading-6')}>{item.excerpt}</p>
        ) : null}
        <span className={cn('inline-flex items-center gap-1.5 pt-5 text-sm font-bold text-brand-700 transition group-hover:text-brand-900', highlight ? 'lg:pt-7' : 'mt-auto')}>
          {t('cta.more')} <ArrowRight className="size-4 transition group-hover:translate-x-1" aria-hidden />
        </span>
      </div>
    </Link>
  )
}
