import { Star } from 'lucide-react'

import { TestimonialCard } from '@/components/cards/TestimonialCard'
import { FinalCta } from '@/components/sections/FinalCta'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Pagination } from '@/components/shared/Pagination'
import { Reveal } from '@/components/shared/Reveal'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useTestimonials } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'

const KINDS = ['text', 'photo', 'video'] as const

export function TestimonialsPage() {
  const { t } = useI18n()
  const { params, page, update } = useListParams(['kind'])
  const kind = params.kind || 'all'
  const { data, isPending, isError, error, refetch } = useTestimonials({ kind, page, page_size: 12 })
  const counts = data?.counts ?? {}
  const chips = [
    { value: 'all', label: t('filter.all'), count: counts.all },
    ...KINDS.map((k) => ({ value: k, label: t(`testimonials.kind.${k}`), count: counts[k] })).filter((c) => c.count || c.value === kind),
  ]
  return (
    <>
      <Seo title={t('testimonials.title')} description={t('testimonials.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('testimonials.title'), path: '/testimonials' }])} />
      <PageHero title={t('testimonials.title')} text={t('testimonials.subtitle')} crumbs={[{ label: t('nav.testimonials') }]}>
        {data?.average_rating ? (
          <p className="mt-6 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 font-bold shadow-soft">
            <Star className="size-5 fill-gold-400 text-gold-400" aria-hidden />
            {t('testimonials.average')}: {data.average_rating.toFixed(1)} / 5
          </p>
        ) : null}
      </PageHero>
      <section className="container-page section">
        {data && data.counts.all > 0 ? <div className="mb-8"><FilterChips chips={chips} value={kind} onChange={(v) => update({ kind: v })} label={t('nav.testimonials')} /></div> : null}
        {isPending ? <CardSkeletons count={6} aspect="aspect-[16/6]" /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : data.results.length ? (
          <>
            <div className="columns-1 gap-6 sm:columns-2 lg:columns-3">
              {data.results.map((item, i) => (
                <Reveal key={item.id} delay={Math.min(i, 6) * 0.05} className="mb-6 break-inside-avoid"><TestimonialCard item={item} /></Reveal>
              ))}
            </div>
            <Pagination page={data.page} total={data.num_pages} onChange={(p) => update({ page: p })} />
          </>
        ) : <EmptyState search={kind !== 'all'} />}
      </section>
      <FinalCta />
    </>
  )
}
