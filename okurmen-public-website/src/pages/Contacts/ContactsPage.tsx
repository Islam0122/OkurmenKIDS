import { ArrowUpRight, Clock, Instagram, Mail, MapPin, MessageCircle, Navigation, Phone, Send, type LucideIcon } from 'lucide-react'
import { useState } from 'react'

import { PageHero } from '@/components/shared/PageHero'
import { crumbsLd, orgLd, Seo } from '@/components/shared/Seo'
import { ErrorState } from '@/components/shared/States'
import { EnrollmentForm } from '@/features/enrollment/EnrollmentForm'
import { useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { Branch } from '@/types/api'
import { cn } from '@/utils/cn'
import { telHref } from '@/utils/format'

/** Map by the branch's real coordinates from the CMS (or its address when none are set). */
function mapEmbed(branch: Branch): string {
  const q = branch.latitude !== null && branch.longitude !== null ? `${branch.latitude},${branch.longitude}` : branch.address
  return `https://maps.google.com/maps?q=${encodeURIComponent(q)}&z=16&output=embed`
}

/** «Маршрут»: the 2GIS / Google Maps link entered in the CMS, else Google directions. */
function directions(branch: Branch): string {
  if (branch.map_url) return branch.map_url
  const q = branch.latitude !== null && branch.longitude !== null ? `${branch.latitude},${branch.longitude}` : branch.address
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(q)}`
}

interface Channel {
  icon: LucideIcon
  label: string
  value: string
  href: string
  tint: string
}

function ChannelCard({ channel }: { channel: Channel }) {
  const external = channel.href.startsWith('http')
  return (
    <li>
      <a
        href={channel.href}
        {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
        className="group flex h-full items-center gap-3 rounded-2xl border border-line bg-white p-3.5 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-soft focus-visible:-translate-y-0.5"
      >
        <span className={cn('grid size-11 shrink-0 place-items-center rounded-xl', channel.tint)}>
          <channel.icon className="size-5" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-bold tracking-wide text-muted uppercase">{channel.label}</span>
          <span className="block font-bold text-ink [overflow-wrap:anywhere]">{channel.value}</span>
        </span>
        <ArrowUpRight className="hidden size-4 shrink-0 text-muted transition group-hover:text-brand-600 sm:block" aria-hidden />
      </a>
    </li>
  )
}

export function ContactsPage() {
  const { t, lang } = useI18n()
  const { data, isPending, isError, error, refetch } = useSettings()
  const [active, setActive] = useState(0)
  const contacts = data?.contacts
  const branches = data?.branches ?? []
  const branch = branches[Math.min(active, Math.max(branches.length - 1, 0))]
  const hours = branch?.working_hours || contacts?.working_hours

  // All values come from the CMS (Сайт → Главная → Контакты / Филиалы): nothing is hardcoded here.
  const channels = [
    contacts?.phone && { icon: Phone, label: t('contacts.phone'), value: contacts.phone, href: telHref(contacts.phone), tint: 'bg-brand-50 text-brand-700' },
    contacts?.whatsapp && { icon: MessageCircle, label: t('contacts.whatsapp'), value: contacts.whatsapp.replace('https://wa.me/', '+'), href: contacts.whatsapp, tint: 'bg-emerald-50 text-emerald-700' },
    contacts?.telegram && { icon: Send, label: t('contacts.telegram'), value: contacts.telegram.replace('https://t.me/', '@'), href: contacts.telegram, tint: 'bg-sky-50 text-sky-700' },
    contacts?.instagram && { icon: Instagram, label: t('contacts.instagram'), value: contacts.instagram.replace(/https:\/\/(www\.)?instagram\.com\//, '@').replace(/\/$/, ''), href: contacts.instagram, tint: 'bg-rose-50 text-rose-600' },
    contacts?.email && { icon: Mail, label: t('contacts.email'), value: contacts.email, href: `mailto:${contacts.email}`, tint: 'bg-gold-50 text-gold-700' },
  ].filter(Boolean) as Channel[]

  return (
    <>
      <Seo
        page="/contacts"
        jsonLd={[orgLd(lang, data), crumbsLd(lang, 'contacts')]}
      />
      <PageHero compact title={t('contacts.heroTitle')} text={t('contacts.heroText')} crumbs={[{ label: t('nav.contacts') }]} />

      <section className="container-page py-8 sm:py-10 lg:py-14">
        {isError ? <ErrorState error={error} onRetry={() => refetch()} className="mb-8" /> : null}
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,27rem)] lg:gap-8 xl:grid-cols-[minmax(0,1fr)_29rem]">
          {/* Left: how to reach us + where we are */}
          <div className="space-y-6">
            <div className="card p-5 sm:p-6">
              <h2 className="text-xl font-extrabold sm:text-2xl">{t('contacts.channels')}</h2>
              {isPending ? (
                <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2" aria-busy="true" aria-label={t('state.loading')}>
                  {Array.from({ length: 4 }, (_, i) => <li key={i} className="h-[4.5rem] animate-pulse rounded-2xl bg-surface-soft" />)}
                </ul>
              ) : channels.length ? (
                <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                  {channels.map((c) => <ChannelCard key={c.label} channel={c} />)}
                </ul>
              ) : null}
            </div>

            {branch ? (
              <div className="card overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5 sm:px-6 sm:pt-6">
                  <h2 className="text-xl font-extrabold sm:text-2xl">{t('contacts.branch')}</h2>
                  {/* Tabs only when the academy has several active branches. */}
                  {branches.length > 1 ? (
                    <div role="tablist" aria-label={t('contacts.branches')} className="flex flex-wrap gap-2">
                      {branches.map((b, i) => (
                        <button key={b.id} type="button" role="tab" aria-selected={i === active} onClick={() => setActive(i)}
                          className={cn('h-10 rounded-full border px-3.5 text-sm font-bold transition', i === active ? 'border-brand-800 bg-brand-800 text-white' : 'border-line bg-white text-ink-soft hover:border-brand-300')}>
                          {b.name}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <dl className="grid gap-3 px-5 py-4 sm:grid-cols-2 sm:px-6">
                  <div className="flex gap-3 sm:col-span-2">
                    <MapPin className="mt-0.5 size-5 shrink-0 text-gold-500" aria-hidden />
                    <div>
                      <dt className="sr-only">{t('contacts.address')}</dt>
                      <dd className="font-bold text-ink">{branch.name}</dd>
                      <dd className="text-ink-soft">{branch.address}</dd>
                    </div>
                  </div>
                  {hours ? (
                    <div className="flex gap-3">
                      <Clock className="mt-0.5 size-5 shrink-0 text-gold-500" aria-hidden />
                      <div><dt className="text-xs font-bold tracking-wide text-muted uppercase">{t('contacts.hours')}</dt><dd className="font-semibold text-ink">{hours}</dd></div>
                    </div>
                  ) : null}
                  {branch.phone ? (
                    <div className="flex gap-3">
                      <Phone className="mt-0.5 size-5 shrink-0 text-gold-500" aria-hidden />
                      <div><dt className="text-xs font-bold tracking-wide text-muted uppercase">{t('contacts.phone')}</dt><dd><a href={telHref(branch.phone)} className="font-semibold text-ink hover:text-brand-700">{branch.phone}</a></dd></div>
                    </div>
                  ) : null}
                </dl>
                <div className="relative">
                  <iframe key={branch.id} title={`${t('contacts.map')}: ${branch.name}`} src={mapEmbed(branch)} loading="lazy" referrerPolicy="no-referrer-when-downgrade"
                    className="block h-56 w-full border-0 bg-brand-50 sm:h-64 lg:h-72" />
                  <a href={directions(branch)} target="_blank" rel="noopener noreferrer"
                    className="absolute right-3 bottom-3 inline-flex h-10 items-center gap-2 rounded-full bg-brand-800 px-4 text-sm font-bold text-white shadow-lift transition hover:bg-brand-700">
                    <Navigation className="size-4" aria-hidden /> {t('cta.route')}
                  </a>
                </div>
              </div>
            ) : hours ? (
              <p className="card flex items-center gap-3 p-5 font-semibold"><Clock className="size-5 text-gold-500" aria-hidden />{t('contacts.hours')}: {hours}</p>
            ) : null}
          </div>

          {/* Right: the form, always in view on desktop */}
          <aside id="enroll" className="scroll-mt-24 lg:sticky lg:top-24">
            <div className="card border-t-4 border-t-gold-400 p-5 sm:p-7">
              <h2 className="text-2xl font-black">{t('contacts.formTitle')}</h2>
              <p className="mt-2 mb-5 text-[15px] text-muted">{t('contacts.formText')}</p>
              <EnrollmentForm compact />
            </div>
          </aside>
        </div>
      </section>
    </>
  )
}
