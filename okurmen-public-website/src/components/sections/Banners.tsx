import { ArrowRight, Megaphone } from 'lucide-react'

import { ButtonLink } from '@/components/shared/Button'
import { SmartImage } from '@/components/shared/SmartImage'
import type { Banner } from '@/types/api'

/** Promotional banners managed in the CMS (shown only within their dates). */
export function Banners({ banners }: { banners: Banner[] }) {
  if (!banners.length) return null
  return (
    <section className="container-page space-y-4 py-6">
      {banners.map((banner, i) => (
        <div key={i} className="flex flex-col overflow-hidden rounded-3xl border border-brand-100 bg-brand-50 sm:flex-row sm:items-center">
          {banner.image ? <SmartImage image={banner.image} alt={banner.title} className="aspect-[16/7] w-full sm:aspect-auto sm:h-36 sm:w-56" /> : null}
          <div className="flex flex-1 flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
            <div className="flex gap-3">
              {!banner.image ? <Megaphone className="mt-1 size-6 shrink-0 text-gold-500" aria-hidden /> : null}
              <div>
                <p className="font-display text-lg font-extrabold">{banner.title}</p>
                {banner.text ? <p className="mt-1 text-sm text-ink-soft">{banner.text}</p> : null}
              </div>
            </div>
            {banner.cta_url ? (
              <ButtonLink to={banner.cta_url} size="sm" variant="secondary">{banner.cta_label || '→'} <ArrowRight className="size-4" aria-hidden /></ButtonLink>
            ) : null}
          </div>
        </div>
      ))}
    </section>
  )
}
