import { Phone } from 'lucide-react'

import logo from '@/assets/logo.png'
import { ButtonLink } from '@/components/shared/Button'
import { Reveal } from '@/components/shared/Reveal'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useSettings } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { telHref } from '@/utils/format'

export function FinalCta({ title }: { title?: string }) {
  const { t } = useI18n()
  const { data } = useSettings()
  const phone = data?.contacts.phone
  return (
    <section className="container-page section">
      <Reveal>
        <div className="relative overflow-hidden rounded-[2rem] bg-gold-400 px-6 py-12 sm:px-12 lg:px-16 lg:py-16">
          <div aria-hidden className="absolute -right-16 -bottom-24 size-80 rounded-full bg-white/25" />
          <div aria-hidden className="absolute top-8 right-40 size-24 rounded-full bg-brand-800/10" />
          <img src={logo} alt="" aria-hidden className="absolute right-10 bottom-10 hidden size-40 rounded-full bg-white p-2 shadow-lift lg:block" />
          <div className="relative max-w-2xl">
            <h2 className="text-3xl leading-tight font-black text-brand-900 sm:text-5xl">{title || t('home.cta.title')}</h2>
            <p className="mt-4 text-lg text-brand-900/80">{t('home.cta.text')}</p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <EnrollButton size="lg" variant="secondary" />
              {phone ? (
                <ButtonLink to={telHref(phone)} size="lg" variant="outline" className="border-brand-900/20 bg-white/60">
                  <Phone className="size-5" aria-hidden /> {phone}
                </ButtonLink>
              ) : null}
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  )
}
