import { CalendarDays, Clock, MapPin, Navigation, Ticket, Users } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { EventCard, PhaseBadge } from '@/components/cards/EventCard'
import { ArticleLayout } from '@/components/layout/ArticleLayout'
import { CardGrid } from '@/components/sections/CardGrid'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { RegistrationForm } from '@/features/events/RegistrationForm'
import { isNotFound, useEvent } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { EventDetail } from '@/types/api'
import { excerpt } from '@/utils/format'
import { absoluteUrl, mediaUrl } from '@/utils/media'

export function EventDetailPage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useEvent(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <EventView event={data} />
}

export function EventView({ event, preview }: { event: EventDetail; preview?: boolean }) {
  const { t, path, formatDate } = useI18n()
  const time = (iso: string) => formatDate(iso, { hour: '2-digit', minute: '2-digit' })
  const sameDay = event.ends_at && new Date(event.ends_at).toDateString() === new Date(event.starts_at).toDateString()
  const when = event.ends_at
    ? sameDay
      ? `${time(event.starts_at)}–${time(event.ends_at)}`
      : `${formatDate(event.starts_at, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })} — ${formatDate(event.ends_at, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}`
    : time(event.starts_at)
  const place = event.location || event.branch
  const mapsQuery = event.branch_address || event.location
  const reg = event.registration

  return (
    <>
      <Seo
        title={event.seo_title || event.title}
        description={event.seo_description || event.excerpt || excerpt(event.body)}
        image={event.cover?.url}
        type="event"
        noindex={preview}
        jsonLd={[
          breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('events.title'), path: '/events' }, { name: event.title, path: `/events/${event.slug}` }]),
          {
            '@context': 'https://schema.org',
            '@type': 'Event',
            name: event.title,
            description: event.excerpt || excerpt(event.body, 300),
            startDate: event.starts_at,
            ...(event.ends_at ? { endDate: event.ends_at } : {}),
            eventStatus: 'https://schema.org/EventScheduled',
            eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
            url: absoluteUrl(path(`/events/${event.slug}`)),
            ...(event.cover ? { image: [absoluteUrl(mediaUrl(event.cover.url) ?? '')] } : {}),
            location: { '@type': 'Place', name: place || 'Okurmen Kids', address: { '@type': 'PostalAddress', streetAddress: event.branch_address || event.location || '', addressCountry: 'KG' } },
            organizer: { '@type': 'EducationalOrganization', name: 'Okurmen Kids Digital', url: absoluteUrl('/') },
            ...(reg.enabled ? { offers: { '@type': 'Offer', price: 0, priceCurrency: 'KGS', availability: reg.open ? 'https://schema.org/InStock' : 'https://schema.org/SoldOut', url: absoluteUrl(path(`/events/${event.slug}`)) } } : {}),
          },
        ]}
      />
      <ArticleLayout
        preview={preview}
        title={event.title}
        lead={event.excerpt}
        crumbs={[{ label: t('nav.events'), to: '/events' }, { label: event.title }]}
        meta={
          <>
            <PhaseBadge phase={event.phase} />
            <span>{t(`events.cat.${event.category}`)}</span>
          </>
        }
        cover={event.cover}
        body={event.body}
        photos={event.photos}
        photosTitle={t('events.gallery')}
        aside={
          <>
            <dl className="card divide-y divide-line">
              <div className="flex gap-3 p-5">
                <CalendarDays className="mt-0.5 size-5 shrink-0 text-brand-400" aria-hidden />
                <div><dt className="text-xs font-bold text-muted uppercase">{t('events.when')}</dt><dd className="font-bold">{formatDate(event.starts_at, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</dd><dd className="flex items-center gap-1.5 text-sm text-ink-soft"><Clock className="size-3.5" aria-hidden />{when}</dd></div>
              </div>
              {place ? (
                <div className="flex gap-3 p-5">
                  <MapPin className="mt-0.5 size-5 shrink-0 text-brand-400" aria-hidden />
                  <div>
                    <dt className="text-xs font-bold text-muted uppercase">{t('events.where')}</dt>
                    <dd className="font-bold">{place}</dd>
                    {event.branch_address && event.branch_address !== place ? <dd className="text-sm text-ink-soft">{event.branch_address}</dd> : null}
                    {mapsQuery ? (
                      <dd><a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(mapsQuery)}`} target="_blank" rel="noopener noreferrer" className="mt-1 -ml-2 inline-flex min-h-10 items-center gap-1.5 rounded-full px-2 text-sm font-bold text-brand-600 hover:bg-brand-50 hover:text-brand-800"><Navigation className="size-3.5" aria-hidden />{t('cta.route')}</a></dd>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </dl>
            {reg.enabled ? (
              <div id="register" className="card p-6">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="flex items-center gap-2 text-xl font-black"><Ticket className="size-5 text-gold-500" aria-hidden />{t('events.registration')}</h2>
                  {reg.spots_left !== null && reg.open ? <span className="flex items-center gap-1 text-sm font-bold text-success"><Users className="size-4" aria-hidden />{t('events.spotsLeft', { count: reg.spots_left })}</span> : null}
                </div>
                {reg.open && !preview ? (
                  <>
                    {reg.deadline ? <p className="mb-4 text-sm text-muted">{t('events.deadline', { date: formatDate(reg.deadline, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }) })}</p> : null}
                    <RegistrationForm slug={event.slug} />
                  </>
                ) : (
                  <p className="rounded-xl bg-surface-soft p-4 text-sm font-semibold text-muted">{reg.open ? t('events.registrationOpen') : t('events.registrationClosed')}</p>
                )}
              </div>
            ) : null}
          </>
        }
        related={event.related.length ? (
          <section className="section bg-surface-soft">
            <div className="container-page">
              <SectionHeader title={t('events.related')} link={{ to: '/events', label: t('cta.allEvents') }} />
              <CardGrid items={event.related} keyOf={(e) => e.slug} render={(e) => <EventCard event={e} />} />
            </div>
          </section>
        ) : null}
      />
    </>
  )
}
