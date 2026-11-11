import { Clock, Instagram, Mail, MapPin, MessageCircle, Navigation, Phone, Send, type LucideIcon } from 'lucide-react'
import { useState } from 'react'

import { PageHero } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { breadcrumbLd, organizationLd, Seo } from '@/components/shared/Seo'
import { ErrorState } from '@/components/shared/States'
import { EnrollmentForm } from '@/features/enrollment/EnrollmentForm'
import { useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { Branch } from '@/types/api'
import { cn } from '@/utils/cn'
import { telHref } from '@/utils/format'

function mapEmbed(branch: Branch): string {
  const q = branch.latitude !== null && branch.longitude !== null ? `${branch.latitude},${branch.longitude}` : branch.address
  return `https://maps.google.com/maps?q=${encodeURIComponent(q)}&z=16&output=embed`
}

function directions(branch: Branch): string {
  if (branch.map_url) return branch.map_url
  const q = branch.latitude !== null && branch.longitude !== null ? `${branch.latitude},${branch.longitude}` : branch.address
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(q)}`
}

export function ContactsPage() {
  const { t } = useI18n()
  const { data, isError, error, refetch } = useSettings()
  const [active, setActive] = useState(0)
  const contacts = data?.contacts
  const branches = data?.branches ?? []
  const branch = branches[Math.min(active, branches.length - 1)]

  const channels = [
    contacts?.phone && { icon: Phone, label: t('contacts.phone'), value: contacts.phone, href: telHref(contacts.phone) },
    contacts?.whatsapp && { icon: MessageCircle, label: t('contacts.whatsapp'), value: contacts.whatsapp.replace('https://wa.me/', '+'), href: contacts.whatsapp },
    contacts?.telegram && { icon: Send, label: t('contacts.telegram'), value: contacts.telegram.replace('https://t.me/', '@'), href: contacts.telegram },
    contacts?.instagram && { icon: Instagram, label: t('contacts.instagram'), value: contacts.instagram.replace(/https:\/\/(www\.)?instagram\.com\//, '@'), href: contacts.instagram },
    contacts?.email && { icon: Mail, label: t('contacts.email'), value: contacts.email, href: `mailto:${contacts.email}` },
  ].filter(Boolean) as { icon: LucideIcon; label: string; value: string; href: string }[]

  return (
    <>
      <Seo
        title={t('contacts.title')}
        description={t('contacts.subtitle')}
        jsonLd={[
          organizationLd({ phone: contacts?.phone, email: contacts?.email, sameAs: [contacts?.instagram ?? null, contacts?.telegram ?? null], addresses: branches.map((b) => b.address) }),
          breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('contacts.title'), path: '/contacts' }]),
        ]}
      />
      <PageHero title={t('contacts.title')} text={t('contacts.subtitle')} crumbs={[{ label: t('nav.contacts') }]} />
      <section className="container-page section">
        {isError ? <ErrorState error={error} onRetry={() => refetch()} className="mb-10" /> : null}
        <div className="grid gap-10 lg:grid-cols-[1fr_440px]">
          <div className="space-y-10">
            {channels.length ? (
              <ul className="grid gap-4 sm:grid-cols-2">
                {channels.map((c, i) => (
                  <Reveal as="li" key={c.label} delay={i * 0.05}>
                    <a href={c.href} {...(c.href.startsWith('http') ? { target: '_blank', rel: 'noopener noreferrer' } : {})} className="card card-hover flex items-center gap-4 p-5">
                      <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-brand-50 text-brand-600"><c.icon className="size-5" aria-hidden /></span>
                      <span className="min-w-0"><span className="block text-xs font-bold text-muted uppercase">{c.label}</span><span className="block truncate font-bold">{c.value}</span></span>
                    </a>
                  </Reveal>
                ))}
              </ul>
            ) : null}
            {contacts?.working_hours ? (
              <p className="flex items-center gap-3 rounded-2xl bg-surface-soft p-5 font-semibold"><Clock className="size-5 text-gold-500" aria-hidden />{t('contacts.hours')}: {contacts.working_hours}</p>
            ) : null}

            {branches.length ? (
              <div>
                <h2 className="mb-5 text-2xl font-black">{t('contacts.branches')}</h2>
                {branches.length > 1 ? (
                  <div role="tablist" aria-label={t('contacts.branches')} className="mb-5 flex flex-wrap gap-2">
                    {branches.map((b, i) => (
                      <button key={b.id} type="button" role="tab" aria-selected={i === active} onClick={() => setActive(i)} className={cn('h-10 rounded-full border px-4 text-sm font-bold', i === active ? 'border-brand-800 bg-brand-800 text-white' : 'border-line bg-white text-ink-soft')}>{b.name}</button>
                    ))}
                  </div>
                ) : null}
                {branch ? (
                  <div className="card overflow-hidden">
                    <iframe key={branch.id} title={`${t('contacts.map')}: ${branch.name}`} src={mapEmbed(branch)} loading="lazy" referrerPolicy="no-referrer-when-downgrade" className="aspect-[16/9] w-full border-0 bg-brand-50" />
                    <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
                      <div className="space-y-1.5">
                        <p className="font-display text-lg font-extrabold">{branch.name}</p>
                        <p className="flex items-start gap-2 text-ink-soft"><MapPin className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden />{branch.address}</p>
                        {branch.phone ? <p className="flex items-center gap-2 text-ink-soft"><Phone className="size-4 text-brand-400" aria-hidden /><a href={telHref(branch.phone)} className="hover:text-brand-800">{branch.phone}</a></p> : null}
                        {branch.working_hours ? <p className="flex items-center gap-2 text-ink-soft"><Clock className="size-4 text-brand-400" aria-hidden />{branch.working_hours}</p> : null}
                      </div>
                      <a href={directions(branch)} target="_blank" rel="noopener noreferrer" className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-full bg-brand-800 px-5 font-bold text-white hover:bg-brand-700">
                        <Navigation className="size-4" aria-hidden /> {t('cta.route')}
                      </a>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <aside id="enroll" className="lg:sticky lg:top-28 lg:self-start">
            <div className="card p-6 sm:p-8">
              <h2 className="text-2xl font-black">{t('contacts.formTitle')}</h2>
              <p className="mt-1.5 mb-6 text-sm text-muted">{t('form.enrollText')}</p>
              <EnrollmentForm compact />
            </div>
          </aside>
        </div>
      </section>
    </>
  )
}
