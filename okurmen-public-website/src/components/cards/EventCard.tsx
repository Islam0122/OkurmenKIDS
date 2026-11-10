import { MapPin, Ticket } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/shared/Badge'
import { SmartImage } from '@/components/shared/SmartImage'
import { useI18n } from '@/i18n'
import type { EventCard as Event } from '@/types/api'
import { cn } from '@/utils/cn'

export function PhaseBadge({ phase }: { phase: Event['phase'] }) {
  const { t } = useI18n()
  const tone = phase === 'ongoing' ? 'green' : phase === 'upcoming' ? 'gold' : 'gray'
  return (
    <Badge tone={tone}>
      {phase === 'ongoing' ? <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden /> : null}
      {t(`events.phase.${phase}`)}
    </Badge>
  )
}

export function EventCard({ event, horizontal }: { event: Event; horizontal?: boolean }) {
  const { t, path, formatDate, locale } = useI18n()
  const start = new Date(event.starts_at)
  const day = start.getDate()
  const month = new Intl.DateTimeFormat(locale, { month: 'short' }).format(start).replace('.', '')
  const time = new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(start)
  return (
    <Link to={path(`/events/${event.slug}`)} className={cn('card card-hover group flex h-full overflow-hidden', horizontal ? 'flex-col sm:flex-row' : 'flex-col', event.phase === 'completed' && 'opacity-90')}>
      <div className={cn('relative overflow-hidden bg-brand-50', horizontal ? 'aspect-[16/10] sm:aspect-auto sm:w-2/5' : 'aspect-[16/10]')}>
        <SmartImage image={event.cover} alt={event.title} className="size-full transition duration-700 group-hover:scale-105" />
        <div className="absolute top-4 left-4 flex flex-col items-center rounded-2xl bg-white px-3 py-2 text-center shadow-soft">
          <span className="font-display text-2xl leading-none font-black text-brand-800">{day}</span>
          <span className="mt-0.5 text-[11px] font-bold tracking-wide text-gold-600 uppercase">{month}</span>
        </div>
      </div>
      <div className="flex flex-1 flex-col p-6">
        <div className="flex flex-wrap items-center gap-2">
          <PhaseBadge phase={event.phase} />
          <span className="text-xs font-bold text-muted">{t(`events.cat.${event.category}`)}</span>
        </div>
        <h3 className="mt-3 text-lg leading-snug font-extrabold">{event.title}</h3>
        {event.excerpt ? <p className="mt-2 line-clamp-2 text-[15px] text-muted">{event.excerpt}</p> : null}
        <div className="mt-auto space-y-1.5 pt-4 text-sm text-ink-soft">
          <p><time dateTime={event.starts_at}>{formatDate(event.starts_at, { weekday: 'long', day: 'numeric', month: 'long' })}, {time}</time></p>
          {event.location || event.branch ? (
            <p className="flex items-center gap-1.5"><MapPin className="size-4 shrink-0 text-brand-400" aria-hidden /><span className="truncate">{event.location ?? event.branch}</span></p>
          ) : null}
          {event.registration_open ? (
            <p className="flex items-center gap-1.5 font-bold text-success"><Ticket className="size-4" aria-hidden />{t('events.registrationOpen')}</p>
          ) : null}
        </div>
      </div>
    </Link>
  )
}
