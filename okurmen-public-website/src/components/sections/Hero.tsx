import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, CheckCircle2, Sparkles } from 'lucide-react'

import logo from '@/assets/logo.png'
import { BRAND } from '@/app/config/site'
import { ButtonLink } from '@/components/shared/Button'
import { SmartImage } from '@/components/shared/SmartImage'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useI18n } from '@/i18n'
import { ru } from '@/i18n/locales/ru'
import type { SiteSettings } from '@/types/api'

/** Pick the CMS text, unless it is just the untranslated Russian default on a ky/en page. */
function cmsOr(value: string | undefined, fallback: string, lang: string, ruDefault: string) {
  if (!value?.trim()) return fallback
  if (lang !== 'ru' && value.trim() === ruDefault) return fallback
  return value
}

export function Hero({ hero }: { hero?: SiteSettings['hero'] }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const title = cmsOr(hero?.title, t('home.hero.title'), lang, ru['home.hero.title'])
  const subtitle = cmsOr(hero?.subtitle, t('home.hero.subtitle'), lang, '')
  const primary = hero?.primary_cta
  const secondary = hero?.secondary_cta
  const appear = (delay: number) => (reduce ? {} : { initial: { opacity: 0, y: 20 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] as const } })

  return (
    <section className="relative overflow-hidden bg-white">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 -right-32 size-[34rem] rounded-full bg-brand-100/70 blur-3xl" />
        <div className="absolute top-1/2 -left-40 size-[26rem] rounded-full bg-gold-100/80 blur-3xl" />
        <svg className="absolute inset-0 size-full opacity-[0.35]" aria-hidden>
          <defs>
            <pattern id="dots" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.2" fill="#d2bdfc" /></pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#dots)" style={{ maskImage: 'radial-gradient(ellipse at 70% 30%, black, transparent 70%)' }} />
        </svg>
      </div>
      <div className="container-page relative grid items-center gap-12 pt-10 pb-16 sm:pt-14 lg:grid-cols-[1.05fr_1fr] lg:gap-8 lg:pt-16 lg:pb-24">
        <div>
          <motion.span {...appear(0)} className="eyebrow">
            <Sparkles className="size-3.5" aria-hidden /> {t('home.hero.eyebrow')}
          </motion.span>
          <motion.h1 {...appear(0.08)} className="mt-6 text-[2.6rem] leading-[1.02] font-black sm:text-6xl lg:text-[4.4rem]">
            {(() => {
              const words = title.trim().split(/\s+/)
              const head = words.slice(0, -1).join(' ')
              const last = words[words.length - 1]
              return (
                <>
                  {head ? `${head} ` : null}
                  <span className="relative inline-block whitespace-nowrap">
                    {last}
                    <svg aria-hidden viewBox="0 0 220 18" className="absolute -bottom-2 left-0 h-3 w-full text-gold-400" preserveAspectRatio="none">
                      <path d="M3 13 C 60 3, 150 3, 217 11" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
                    </svg>
                  </span>
                </>
              )
            })()}
          </motion.h1>
          <motion.p {...appear(0.16)} className="mt-7 max-w-xl text-lg leading-relaxed text-ink-soft sm:text-xl">{subtitle}</motion.p>
          <motion.div {...appear(0.24)} className="mt-9 flex flex-col gap-3 sm:flex-row">
            {primary?.url ? (
              <ButtonLink to={primary.url} size="lg">{primary.label || t('cta.enroll')} <ArrowRight className="size-5" aria-hidden /></ButtonLink>
            ) : (
              <EnrollButton size="lg" label={primary?.label || undefined} />
            )}
            <ButtonLink to={secondary?.url || '/courses'} size="lg" variant="outline">{secondary?.label || t('cta.courses')}</ButtonLink>
          </motion.div>
          <motion.ul {...appear(0.32)} className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-sm font-semibold text-ink-soft">
            {(['home.hero.trust1', 'home.hero.trust2', 'home.hero.trust3'] as const).map((key) => (
              <li key={key} className="flex items-center gap-2"><CheckCircle2 className="size-5 text-gold-500" aria-hidden />{t(key)}</li>
            ))}
          </motion.ul>
        </div>

        <motion.div {...(reduce ? {} : { initial: { opacity: 0, scale: 0.96 }, animate: { opacity: 1, scale: 1 }, transition: { duration: 0.8, delay: 0.15 } })} className="relative mx-auto w-full max-w-xl">
          {hero?.image ? (
            <div className="relative overflow-hidden rounded-[2rem] shadow-lift ring-8 ring-white">
              <SmartImage image={hero.image} alt={BRAND.name} priority sizes="(min-width: 1024px) 45vw, 100vw" className="aspect-[5/4] w-full" />
            </div>
          ) : (
            <CodeIllustration caption={t('home.hero.codeCaption')} />
          )}
          <div className="absolute -bottom-6 -left-2 flex items-center gap-3 rounded-2xl bg-white p-3 pr-5 shadow-lift sm:-left-8 motion-safe:animate-float">
            <img src={logo} alt="" className="size-12 rounded-full" width={48} height={43} />
            <span className="font-display text-sm leading-tight font-extrabold text-brand-800">{BRAND.tagline}</span>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

/** Brand illustration (not a photo) when no hero photo is uploaded in the CMS. */
function CodeIllustration({ caption }: { caption: string }) {
  const lines: [string, string][] = [
    ['text-brand-300', '# main.py'],
    ['text-gold-300', 'name = input("Как тебя зовут? ")'],
    ['text-white', 'print(f"Привет, {name}!")'],
    ['', ''],
    ['text-sky-300', 'for level in range(1, 4):'],
    ['text-white', '    print("⭐" * level)'],
  ]
  return (
    <figure className="relative">
      <div className="absolute -inset-4 -rotate-3 rounded-[2.25rem] bg-gold-400" aria-hidden />
      <div className="relative overflow-hidden rounded-[2rem] bg-brand-900 shadow-lift">
        <div className="flex items-center gap-2 border-b border-white/10 px-5 py-4">
          <span className="size-3 rounded-full bg-rose-400" /><span className="size-3 rounded-full bg-gold-400" /><span className="size-3 rounded-full bg-emerald-400" />
          <span className="ml-3 text-xs font-semibold text-white/50">okurmen-kids — python</span>
        </div>
        <pre className="overflow-hidden px-6 py-6 font-mono text-[13px] leading-7 sm:text-[15px]" aria-hidden>
          {lines.map(([cls, text], i) => (
            <div key={i} className="flex gap-4"><span className="w-4 text-right text-white/25 select-none">{i + 1}</span><span className={cls}>{text}</span></div>
          ))}
          <div className="mt-3 rounded-xl bg-white/5 p-4 text-emerald-300">
            <div>Привет, Айгерим!</div><div>⭐</div><div>⭐⭐</div><div>⭐⭐⭐</div>
          </div>
        </pre>
      </div>
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  )
}
