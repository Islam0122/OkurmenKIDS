import { Reveal } from '@/components/shared/Reveal'
import { useI18n } from '@/i18n'
import type { SiteSettings } from '@/types/api'

/** Academy numbers — only what marketing entered in the CMS (nothing invented). */
export function Stats({ stats, title }: { stats: SiteSettings['stats']; title?: string }) {
  const { t } = useI18n()
  if (!stats.length) return null
  return (
    <section aria-label={title || t('home.stats.title')} className="container-page py-6">
      <div className="relative overflow-hidden rounded-[2rem] bg-brand-800 px-6 py-10 text-white sm:px-10 lg:py-12">
        <div aria-hidden className="absolute -top-20 -right-10 size-64 rounded-full bg-gold-400/20 blur-3xl" />
        <ul className="relative grid grid-cols-2 gap-x-6 gap-y-10 lg:grid-cols-4">
          {stats.map((stat, i) => (
            <Reveal as="li" key={i} delay={i * 0.06} className="text-center lg:text-left">
              <p className="font-display text-4xl font-black text-gold-400 sm:text-5xl">{stat.value}</p>
              <p className="mt-2 text-sm font-semibold text-white/75 sm:text-base">{stat.label}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}
