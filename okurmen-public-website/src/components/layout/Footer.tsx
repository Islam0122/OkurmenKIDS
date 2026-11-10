import { Clock, Instagram, Mail, MapPin, MessageCircle, Phone, Send } from 'lucide-react'
import { Link } from 'react-router-dom'

import { BRAND, NAV } from '@/app/config/site'
import { Logo } from '@/components/shared/Logo'
import { useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { telHref } from '@/utils/format'

export function Footer() {
  const { t, path } = useI18n()
  const { data } = useSettings()
  const contacts = data?.contacts
  const socials = [
    { href: contacts?.instagram, label: t('contacts.instagram'), icon: Instagram },
    { href: contacts?.telegram, label: t('contacts.telegram'), icon: Send },
    { href: contacts?.whatsapp, label: t('contacts.whatsapp'), icon: MessageCircle },
  ].filter((s) => s.href)

  return (
    <footer className="relative overflow-hidden bg-brand-900 text-white">
      <div aria-hidden className="pointer-events-none absolute -top-40 right-0 size-[28rem] rounded-full bg-brand-600/30 blur-3xl" />
      <div className="container-page relative grid gap-12 py-16 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1.2fr] lg:py-20">
        <div>
          <Logo inverted />
          <p className="mt-5 max-w-sm text-sm leading-relaxed text-white/70">{t('footer.about')}</p>
          <p className="mt-5 font-display text-lg font-extrabold text-gold-300">{BRAND.tagline}</p>
          {socials.length ? (
            <div className="mt-6">
              <p className="sr-only">{t('footer.follow')}</p>
              <ul className="flex gap-2">
                {socials.map((s) => (
                  <li key={s.label}>
                    <a href={s.href!} target="_blank" rel="noopener noreferrer" aria-label={s.label} className="grid size-11 place-items-center rounded-full bg-white/10 transition hover:bg-gold-400 hover:text-brand-900">
                      <s.icon className="size-5" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <nav aria-label={t('footer.sections')}>
          <p className="font-display text-sm font-extrabold tracking-wider text-gold-300 uppercase">{t('footer.sections')}</p>
          <ul className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            {NAV.map((item) => (
              <li key={item.path}>
                <Link to={path(item.path)} className="text-white/75 transition hover:text-white">{t(item.label)}</Link>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <p className="font-display text-sm font-extrabold tracking-wider text-gold-300 uppercase">{t('footer.contacts')}</p>
          <ul className="mt-5 space-y-3.5 text-sm text-white/80">
            {contacts?.phone ? (
              <li className="flex gap-3"><Phone className="mt-0.5 size-4 shrink-0 text-gold-300" aria-hidden /><a href={telHref(contacts.phone)} className="hover:text-white">{contacts.phone}</a></li>
            ) : null}
            {contacts?.email ? (
              <li className="flex gap-3"><Mail className="mt-0.5 size-4 shrink-0 text-gold-300" aria-hidden /><a href={`mailto:${contacts.email}`} className="hover:text-white">{contacts.email}</a></li>
            ) : null}
            {data?.branches.map((branch) => (
              <li key={branch.id} className="flex gap-3"><MapPin className="mt-0.5 size-4 shrink-0 text-gold-300" aria-hidden /><span><span className="font-semibold text-white">{branch.name}</span><br />{branch.address}</span></li>
            ))}
            {contacts?.working_hours ? (
              <li className="flex gap-3"><Clock className="mt-0.5 size-4 shrink-0 text-gold-300" aria-hidden />{contacts.working_hours}</li>
            ) : null}
          </ul>
          <Link to={path('/contacts')} className="mt-6 inline-flex font-bold text-gold-300 hover:text-gold-200">{t('cta.contactUs')} →</Link>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="container-page flex flex-col gap-2 py-6 text-xs text-white/50 sm:flex-row sm:items-center sm:justify-between">
          <p>{t('footer.rights', { year: new Date().getFullYear() })}</p>
          <p>{t('brand.descriptor')} · Кыргызстан</p>
        </div>
      </div>
    </footer>
  )
}
