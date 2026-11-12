import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, Code2, ShieldCheck, Zap } from 'lucide-react'

import { BRAND } from '@/app/config/site'
import { LaptopIllustration } from '@/components/home/LaptopIllustration'
import { buttonClass, ButtonLink } from '@/components/shared/Button'
import { SmartImage } from '@/components/shared/SmartImage'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useI18n } from '@/i18n'
import { ru } from '@/i18n/locales/ru'
import type { SiteSettings } from '@/types/api'
import { cn } from '@/utils/cn'

/** Pick the CMS text, unless it is just the untranslated Russian default on a ky/en page. */
function cmsOr(value: string | undefined, fallback: string, lang: string, ruDefault: string) {
  if (!value?.trim()) return fallback
  if (lang !== 'ru' && value.trim() === ruDefault) return fallback
  return value
}

const BENEFITS = [
  { key: 'home.hero.benefit1', icon: Code2 },
  { key: 'home.hero.benefit2', icon: Zap },
  { key: 'home.hero.benefit3', icon: ShieldCheck },
] as const

/**
 * Homepage hero. Texts and buttons can be overridden in the CMS («Главная» →
 * hero); without CMS values the approved defaults below are used. The right
 * side is the coding illustration, or the CMS hero photo if marketing uploads one.
 */
export function Hero({ hero, programsHref = '/courses' }: { hero?: SiteSettings['hero']; programsHref?: string }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const title = cmsOr(hero?.title, t('home.hero.title'), lang, ru['home.hero.title'])
  const lead = cmsOr(hero?.subtitle, t('home.hero.lead'), lang, '')
  const primary = hero?.primary_cta
  const secondary = hero?.secondary_cta
  const appear = (delay: number) => (reduce ? {} : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] as const } })
  const words = title.trim().split(/\s+/)
  const head = words.slice(0, -1).join(' ')
  const last = words[words.length - 1]
  const secondaryHref = secondary?.url || programsHref
  const secondaryLabel = secondary?.label || t('home.hero.secondary')

  return (
    <section className="relative overflow-hidden bg-white">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-48 right-[-10%] size-[42rem] rounded-full bg-[radial-gradient(closest-side,#efe8ff,transparent)]" />
        <div className="absolute bottom-[-12rem] left-[-8rem] size-[30rem] rounded-full bg-[radial-gradient(closest-side,#fff4d6,transparent)]" />
      </div>
      <div className="relative mx-auto grid w-full max-w-[1280px] items-center gap-10 px-4 pt-8 pb-12 sm:px-6 sm:pt-12 md:pb-16 lg:grid-cols-[1.1fr_1fr] lg:gap-4 lg:px-8 lg:pt-12 lg:pb-14">
        <div className="max-w-xl">
          <motion.span {...appear(0)} className="inline-flex items-center rounded-full bg-[#efe9fb] px-3.5 py-1.5 text-sm font-bold text-kids-primary">
            {t('home.hero.badge')}
          </motion.span>
          {/* No entrance animation on the headline: it is the LCP element, so it must paint at once. */}
          <h1 className="mt-5 font-display text-[2.6rem] leading-[1.05] font-black tracking-[-0.02em] text-kids-primary sm:text-6xl lg:text-[4.1rem]">
            {head ? `${head} ` : null}
            <span className="relative inline-block whitespace-nowrap">
              <span aria-hidden className="absolute inset-x-[-0.08em] bottom-[0.06em] -z-0 h-[0.42em] -skew-x-6 rounded-md bg-kids-yellow" />
              <span className="relative">{last}</span>
              <svg aria-hidden viewBox="0 0 40 40" className="absolute -top-[0.35em] -right-[0.75em] w-[0.6em] text-kids-yellow">
                <path d="M8 30 L16 18 M20 32 L30 8 M32 34 L38 24" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
              </svg>
            </span>
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-kids-muted sm:text-lg">{lead}</p>
          <motion.div {...appear(0.18)} className="mt-7 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            {primary?.url ? (
              <ButtonLink to={primary.url} size="md" className="sm:h-13 sm:px-7">{primary.label || t('home.hero.primary')} <ArrowRight className="size-5" aria-hidden /></ButtonLink>
            ) : (
              <EnrollButton size="md" className="sm:h-13 sm:px-7" label={primary?.label || t('home.hero.primary')} />
            )}
            {secondaryHref.startsWith('#') ? (
              <a href={secondaryHref} className={buttonClass('outline', 'md', 'sm:h-13 sm:px-7')}>{secondaryLabel}</a>
            ) : (
              <ButtonLink to={secondaryHref} size="md" variant="outline" className="sm:h-13 sm:px-7">{secondaryLabel}</ButtonLink>
            )}
          </motion.div>
          <motion.ul {...appear(0.24)} className="mt-8 grid grid-cols-1 gap-3 min-[420px]:grid-cols-3 sm:gap-5">
            {BENEFITS.map(({ key, icon: Icon }) => (
              <li key={key} className="flex items-center gap-2.5 text-sm leading-snug font-bold text-kids-text">
                <Icon className="size-6 shrink-0 text-kids-yellow" strokeWidth={2.25} aria-hidden />
                {t(key)}
              </li>
            ))}
          </motion.ul>
        </div>

        <motion.div {...(reduce ? {} : { initial: { opacity: 0, scale: 0.97 }, animate: { opacity: 1, scale: 1 }, transition: { duration: 0.7, delay: 0.1 } })} className={cn('relative w-full', hero?.image ? 'mx-auto max-w-xl' : '')}>
          {hero?.image ? (
            <div className="relative overflow-hidden rounded-[2rem] shadow-lift ring-8 ring-white">
              <SmartImage image={hero.image} alt={BRAND.name} priority sizes="(min-width: 1024px) 45vw, 100vw" className="aspect-[5/4] w-full" />
            </div>
          ) : (
            <LaptopIllustration />
          )}
        </motion.div>
      </div>
    </section>
  )
}
