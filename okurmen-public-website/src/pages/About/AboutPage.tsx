import { Check, Compass, Eye, HeartHandshake, Lightbulb, Rocket, Sparkles, Star, Target, Users } from 'lucide-react'

import { Stats } from '@/components/sections/Stats'
import { FinalCta } from '@/components/sections/FinalCta'
import { PageHero } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { breadcrumbLd, organizationLd, Seo } from '@/components/shared/Seo'
import { Gallery } from '@/features/content/Gallery'
import { RichText } from '@/features/content/RichText'
import { useAchievements, useEvents, useSettings } from '@/hooks/queries'
import { useI18n, type MessageKey } from '@/i18n'
import type { ImageAsset } from '@/types/api'

const PHILOSOPHY = [
  { icon: Rocket, key: 1 },
  { icon: Lightbulb, key: 2 },
  { icon: Users, key: 3 },
  { icon: Compass, key: 4 },
] as const

const VALUES = [
  { icon: Sparkles, key: 'curiosity' },
  { icon: HeartHandshake, key: 'care' },
  { icon: Star, key: 'quality' },
  { icon: Eye, key: 'openness' },
] as const

export function AboutPage() {
  const { t } = useI18n()
  const settings = useSettings()
  const events = useEvents({ phase: 'completed', page_size: 6 })
  const achievements = useAchievements({ page_size: 6 })
  const about = settings.data?.about
  const photos: ImageAsset[] = [
    ...(events.data?.results ?? []).map((e) => e.cover),
    ...(achievements.data?.results ?? []).map((a) => a.cover),
  ].filter((p): p is ImageAsset => Boolean(p)).slice(0, 7)

  return (
    <>
      <Seo title={t('about.title')} description={t('about.subtitle')} jsonLd={[organizationLd(), breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('about.title'), path: '/about' }])]} />
      <PageHero title={t('about.title')} text={t('about.subtitle')} crumbs={[{ label: t('nav.about') }]} />

      {about?.story ? (
        <section className="section">
          <div className="container-page grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
            <Reveal><h2 className="text-section-title font-black">{t('about.story')}</h2></Reveal>
            <Reveal delay={0.1}><RichText source={about.story} /></Reveal>
          </div>
        </section>
      ) : null}

      {about?.mission || about?.vision ? (
        <section className="container-page grid gap-6 pb-6 md:grid-cols-2">
          {about.mission ? (
            <Reveal className="rounded-[2rem] bg-brand-800 p-8 text-white sm:p-10">
              <Target className="size-10 text-gold-400" aria-hidden />
              <h2 className="mt-5 text-2xl font-black text-white">{t('about.mission')}</h2>
              <p className="mt-3 text-lg leading-relaxed whitespace-pre-line text-white/85">{about.mission}</p>
            </Reveal>
          ) : null}
          {about.vision ? (
            <Reveal delay={0.08} className="rounded-[2rem] bg-gold-400 p-8 sm:p-10">
              <Eye className="size-10 text-brand-800" aria-hidden />
              <h2 className="mt-5 text-2xl font-black">{t('about.vision')}</h2>
              <p className="mt-3 text-lg leading-relaxed whitespace-pre-line text-brand-900/85">{about.vision}</p>
            </Reveal>
          ) : null}
        </section>
      ) : null}

      <section className="section">
        <div className="container-page">
          <SectionHeader align="center" title={t('about.philosophy.title')} />
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {PHILOSOPHY.map(({ icon: Icon, key }, i) => (
              <Reveal key={key} delay={i * 0.06} className="card p-7">
                <span className="grid size-12 place-items-center rounded-2xl bg-brand-50 text-brand-600"><Icon className="size-6" aria-hidden /></span>
                <h3 className="mt-5 text-lg font-extrabold">{t(`about.philosophy.${key}.title` as MessageKey)}</h3>
                <p className="mt-2 text-[15px] text-muted">{t(`about.philosophy.${key}.text` as MessageKey)}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {settings.data?.stats.length ? <Stats stats={settings.data.stats} /> : null}

      <section className="section">
        <div className="container-page grid gap-12 lg:grid-cols-2">
          <div>
            <SectionHeader title={t('about.method.title')} />
            <ol className="relative space-y-8 border-l-2 border-dashed border-brand-200 pl-8">
              {[1, 2, 3, 4].map((n, i) => (
                <Reveal as="li" key={n} delay={i * 0.06} className="relative">
                  <span className="absolute top-0 -left-[3.05rem] grid size-10 place-items-center rounded-full bg-gold-400 font-display font-black text-brand-900 ring-4 ring-white">{n}</span>
                  <h3 className="text-lg font-extrabold">{t(`about.method.${n}` as MessageKey)}</h3>
                  <p className="mt-1 text-muted">{t(`about.method.${n}.text` as MessageKey)}</p>
                </Reveal>
              ))}
            </ol>
          </div>
          <div>
            <SectionHeader title={t('about.values.title')} />
            <div className="grid gap-4 sm:grid-cols-2">
              {VALUES.map(({ icon: Icon, key }, i) => (
                <Reveal key={key} delay={i * 0.06} className="rounded-3xl bg-surface-purple p-6">
                  <Icon className="size-7 text-brand-600" aria-hidden />
                  <h3 className="mt-3 font-extrabold">{t(`about.values.${key}`)}</h3>
                  <p className="mt-1 text-sm text-muted">{t(`about.values.${key}.text` as MessageKey)}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {photos.length >= 3 ? (
        <section className="section bg-surface-soft">
          <div className="container-page">
            <SectionHeader title="Okurmen Kids" text={t('home.video.text')} />
            <Gallery photos={photos} title="Okurmen Kids" />
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="container-page">
          <SectionHeader align="center" title={t('about.why.title')} />
          <ul className="mx-auto grid max-w-4xl gap-4 sm:grid-cols-2">
            {[1, 2, 3, 4, 5, 6].map((n, i) => (
              <Reveal as="li" key={n} delay={i * 0.04} className="flex items-start gap-3 rounded-2xl border border-line bg-white p-5">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-gold-400 text-brand-900"><Check className="size-4" strokeWidth={3} aria-hidden /></span>
                <span className="font-semibold text-ink-soft">{t(`about.why.${n}` as MessageKey)}</span>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>
      <FinalCta />
    </>
  )
}
