import {
  ArrowRight, Award, CalendarCheck, ChevronDown, Compass, Eye, FolderKanban, GraduationCap, HeartHandshake, Lightbulb,
  LineChart, MapPin, Rocket, Sparkles, Star, Target, Users, type LucideIcon,
} from 'lucide-react'
import { useQueries } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { TeamCard } from '@/components/cards/TeamCard'
import { Stars, TestimonialCard } from '@/components/cards/TestimonialCard'
import { FinalCta } from '@/components/sections/FinalCta'
import { buttonClass, ButtonLink } from '@/components/shared/Button'
import { Breadcrumbs } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { crumbsLd, orgLd, Seo } from '@/components/shared/Seo'
import { Gallery } from '@/features/content/Gallery'
import { RichText } from '@/features/content/RichText'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useAchievements, useCourses, useEvents, useNews, useProjects, useSettings, useTeam, useTestimonials } from '@/hooks/queries'
import { useI18n, type MessageKey } from '@/i18n'
import { siteApi } from '@/services/endpoints'
import type { ImageAsset, NewsCategory } from '@/types/api'
import { cn } from '@/utils/cn'
import { isTeacher } from '@/utils/team'

import { PROGRAMS, programTarget } from '@/features/programs/programs'
import heroStudents from '@/assets/about/hero-students.webp'
import heroStudents768 from '@/assets/about/hero-students-768.webp'

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

/** «Почему родители выбирают нас» — each claim points to where it can be checked on the site. */
const WHY: { n: 1 | 2 | 3 | 4 | 5 | 6; icon: LucideIcon; to?: string }[] = [
  { n: 1, icon: GraduationCap },
  { n: 2, icon: Users, to: '#trainers' },
  { n: 3, icon: FolderKanban, to: '/projects' },
  { n: 4, icon: LineChart },
  { n: 5, icon: Award, to: '/achievements' },
  { n: 6, icon: MapPin, to: '/contacts' },
]

const STAT_ICONS: LucideIcon[] = [Users, CalendarCheck, HeartHandshake, Award]

/** News that report something that happened at the academy — their covers are event photos. Announcements and education posts often use illustrations. */
const PHOTO_NEWS: NewsCategory[] = ['events', 'achievements', 'competitions', 'activities']


/** CMS text can carry invisible characters (e.g. a zero-width space pasted before the address) that `trim()` keeps. */
const clean = (value: string) => value.replace(/[\u200B-\u200D\u2060\uFEFF]/g, '').trim()

export function AboutPage() {
  const { t, path, lang } = useI18n()
  const settings = useSettings()
  const courses = useCourses()
  const projects = useProjects({ page_size: 1 })
  const team = useTeam()
  const testimonials = useTestimonials({ page_size: 3 })
  const events = useEvents({ phase: 'completed', page_size: 6 })
  const achievements = useAchievements({ page_size: 6 })
  const news = useNews({ page_size: 12 })
  // Photos inside each achievement (same query key as the achievement page, so the cache is shared).
  const achievementDetails = useQueries({
    queries: (achievements.data?.results ?? []).filter((a) => a.photo_count > 0).slice(0, 4).map((a) => ({
      queryKey: ['achievement', a.slug, lang],
      queryFn: () => siteApi.achievement(a.slug),
    })),
  })

  const about = settings.data?.about
  const branch = settings.data?.branches[0]
  const phone = settings.data?.contacts.phone

  // Authentic academy photos only — completed events, achievements (covers + albums) and event-type
  // news, with the event's title as alt text. Announcement/education covers are left out (illustrations).
  const photos: ImageAsset[] = [
    ...(events.data?.results ?? []).map((e) => ({ image: e.cover, title: e.title })),
    ...(achievements.data?.results ?? []).map((a) => ({ image: a.cover, title: a.title })),
    ...achievementDetails.flatMap((q) => (q.data?.photos ?? []).map((image) => ({ image, title: q.data!.title }))),
    ...(news.data?.results ?? []).filter((n) => PHOTO_NEWS.includes(n.category)).map((n) => ({ image: n.cover, title: n.title })),
  ]
    .filter((p): p is { image: ImageAsset; title: string } => Boolean(p.image))
    .map(({ image, title }) => ({ ...image, caption: image.caption || title }))
    .filter((p, i, all) => all.findIndex((q) => q.url === p.url) === i)
  const gallery = photos.slice(0, 7)
  const trainers = (team.data?.results ?? []).filter(isTeacher)
  const reviews = testimonials.data?.results ?? []
  const programNames = PROGRAMS.map((p) => t(`about.programs.${p.id}.title` as MessageKey)).join(', ')

  const faq = [
    { q: t('about.faq.1.q'), a: t('about.faq.1.a') },
    { q: t('about.faq.2.q'), a: t('about.faq.2.a', { programs: programNames }) },
    { q: t('about.faq.3.q'), a: t('about.faq.3.a') },
    { q: t('about.faq.4.q'), a: t('about.faq.4.a') },
    {
      q: t('about.faq.5.q'),
      a: branch ? t('about.faq.5.a', { name: clean(branch.name), address: clean(branch.address), hours: clean(branch.working_hours) }) : t('about.faq.5.aNone'),
    },
    { q: t('about.faq.6.q'), a: phone ? t('about.faq.6.a', { phone }) : t('about.faq.6.aNoPhone') },
  ]
  const faqLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faq.map(({ q, a }) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })),
  }

  return (
    <>
      <Seo
        page="/about"
        image={heroStudents}
        jsonLd={[orgLd(lang, settings.data), crumbsLd(lang, 'about'), faqLd]}
      />

      {/* 1. Hero */}
      <section className="relative overflow-hidden bg-surface-purple">
        <div aria-hidden className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-gold-200/50 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-40 -left-24 size-96 rounded-full bg-brand-200/40 blur-3xl" />
        <div className="container-page relative grid items-center gap-10 pt-8 pb-14 sm:pt-10 lg:grid-cols-[1.2fr_0.8fr] lg:gap-12 xl:gap-16 lg:pb-20">
          <div>
            <Breadcrumbs crumbs={[{ label: t('nav.about') }]} />
            <p className="eyebrow mt-6">{t('about.title')}</p>
            <h1 className="mt-4 max-w-2xl text-page-title font-black text-balance">{t('about.hero.title')}</h1>
            <p className="mt-5 max-w-xl text-lg text-ink-soft">{t('about.hero.text')}</p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <a href="#approach" className={buttonClass('primary', 'lg')}>
                {t('about.hero.cta')} <ArrowRight className="size-5" aria-hidden />
              </a>
              <ButtonLink to="/projects" variant="outline" size="lg">{t('about.hero.projects')}</ButtonLink>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-xl lg:max-w-none">
            <div aria-hidden className="absolute -top-4 -right-4 size-24 rounded-3xl bg-gold-400 sm:-top-6 sm:-right-6 sm:size-32" />
            <div aria-hidden className="absolute -bottom-4 -left-4 size-20 rounded-full border-8 border-brand-200/70 sm:size-28" />
            {/* 3:2 source — shown whole on phones, cropped to 4:3 from tablet up with the group kept in frame. */}
            <img
              src={heroStudents}
              srcSet={`${heroStudents768} 768w, ${heroStudents} 1536w`}
              sizes="(min-width: 1024px) 560px, (min-width: 640px) 576px, 100vw"
              width={1536}
              height={1024}
              alt={t('about.hero.photoAlt')}
              loading="eager"
              decoding="async"
              fetchPriority="high"
              className="relative aspect-[3/2] w-full rounded-[2rem] bg-brand-50 object-cover object-[58%_40%] shadow-lift ring-8 ring-white sm:aspect-[4/3]"
            />
            {settings.data?.stats[0] ? (
              <div className="absolute -bottom-6 left-4 flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-lift sm:left-8 sm:px-5 sm:py-4">
                <span className="grid size-11 place-items-center rounded-xl bg-brand-800 text-gold-400"><GraduationCap className="size-6" aria-hidden /></span>
                <span>
                  <span className="block font-display text-2xl leading-none font-black text-brand-800">{settings.data.stats[0].value}</span>
                  <span className="mt-1 block text-sm font-semibold text-muted">{settings.data.stats[0].label}</span>
                </span>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {/* 2. Statistics — CMS values only (Settings → stats), never typed in here */}
      {settings.data?.stats.length ? (
        <section aria-labelledby="about-stats" className="container-page pt-16 sm:pt-20">
          <div className="relative overflow-hidden rounded-[2rem] bg-brand-800 px-6 py-10 text-white sm:px-10 lg:px-14 lg:py-12">
            <div aria-hidden className="absolute -top-24 -right-16 size-72 rounded-full bg-gold-400/20 blur-3xl" />
            <div aria-hidden className="absolute -bottom-24 -left-10 size-56 rounded-full bg-brand-500/30 blur-3xl" />
            <h2 id="about-stats" className="relative text-sm font-bold tracking-[0.14em] text-white/70 uppercase">{t('about.stats.title')}</h2>
            <ul className={cn('relative mt-6 grid gap-8 sm:gap-6', settings.data.stats.length >= 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
              {settings.data.stats.map((stat, i) => {
                const Icon = STAT_ICONS[i % STAT_ICONS.length]
                return (
                  <Reveal as="li" key={i} delay={i * 0.06} className="flex items-center gap-4 sm:border-l sm:border-white/15 sm:pl-6 sm:first:border-l-0 sm:first:pl-0">
                    <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-white/10 text-gold-400"><Icon className="size-7" aria-hidden /></span>
                    <span>
                      <span className="block font-display text-4xl leading-none font-black text-gold-400 sm:text-5xl">{stat.value}</span>
                      <span className="mt-2 block text-base font-semibold text-white/80">{stat.label}</span>
                    </span>
                  </Reveal>
                )
              })}
            </ul>
          </div>
        </section>
      ) : null}

      {/* CMS story / mission / vision (shown when marketing fills them in) */}
      {about?.story ? (
        <section className="section">
          <div className="container-page grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
            <Reveal><h2 className="text-section-title font-black">{t('about.story')}</h2></Reveal>
            <Reveal delay={0.1}><RichText source={about.story} /></Reveal>
          </div>
        </section>
      ) : null}
      {about?.mission || about?.vision ? (
        <section className="container-page grid gap-6 pt-12 md:grid-cols-2">
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

      {/* 4. Our approach */}
      <section id="approach" className="section scroll-mt-24">
        <div className="container-page">
          <SectionHeader align="center" title={t('about.philosophy.title')} text={t('about.philosophy.text')} />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
            {PHILOSOPHY.map(({ icon: Icon, key }, i) => (
              <Reveal key={key} delay={i * 0.06} className="card card-hover flex h-full flex-col p-7 sm:p-8">
                <span className="grid size-16 place-items-center rounded-2xl bg-brand-800 text-gold-400 shadow-soft">
                  <Icon className="size-8" strokeWidth={1.75} aria-hidden />
                </span>
                <span aria-hidden className="mt-6 font-display text-sm font-black text-gold-600">0{key}</span>
                <h3 className="mt-1 text-xl leading-snug font-extrabold">{t(`about.philosophy.${key}.title` as MessageKey)}</h3>
                <p className="mt-3 text-[15px] leading-relaxed text-muted">{t(`about.philosophy.${key}.text` as MessageKey)}</p>
              </Reveal>
            ))}
          </div>
          <ul className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label={t('about.values.title')}>
            {VALUES.map(({ icon: Icon, key }) => (
              <li key={key} className="flex items-start gap-3 rounded-2xl bg-surface-purple p-4">
                <Icon className="mt-0.5 size-5 shrink-0 text-brand-600" aria-hidden />
                <span>
                  <span className="block font-extrabold">{t(`about.values.${key}`)}</span>
                  <span className="block text-sm text-muted">{t(`about.values.${key}.text` as MessageKey)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 5. What children learn */}
      <section className="section bg-surface-soft">
        <div className="container-page">
          <SectionHeader title={t('about.programs.title')} text={t('about.programs.text')} />
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6">
            {PROGRAMS.map((program, i) => {
              const Icon = program.icon
              const target = programTarget(program, courses.data?.results ?? [], projects.data?.counts ?? {})
              const title = t(`about.programs.${program.id}.title` as MessageKey)
              return (
                <Reveal as="li" key={program.id} delay={i * 0.05} className="card card-hover flex h-full flex-col p-6 sm:p-7">
                  <span className={cn('grid size-14 place-items-center rounded-2xl', program.tone)}>
                    <Icon className="size-7" strokeWidth={1.75} aria-hidden />
                  </span>
                  <h3 className="mt-5 text-xl font-extrabold">{title}</h3>
                  <p className="mt-2 flex-1 text-[15px] leading-relaxed text-muted">{t(`about.programs.${program.id}.text` as MessageKey)}</p>
                  <div className="mt-5 border-t border-line pt-4">
                    {target.kind === 'enroll' ? (
                      <EnrollButton variant="outline" size="sm" label={t('about.programs.ask')} />
                    ) : (
                      <Link to={path(target.to)} className={buttonClass('outline', 'sm')} aria-label={`${title} — ${target.kind === 'course' ? t('cta.more') : t('about.programs.projects')}`}>
                        {target.kind === 'course' ? t('cta.more') : t('about.programs.projects')}
                        <ArrowRight className="size-4" aria-hidden />
                      </Link>
                    )}
                  </div>
                </Reveal>
              )
            })}
          </ul>
        </div>
      </section>

      {/* 6. Student journey */}
      <section className="section">
        <div className="container-page">
          <SectionHeader align="center" title={t('about.method.title')} text={t('about.method.text')} />
          <ol className="relative grid gap-8 lg:grid-cols-4 lg:gap-6">
            <span aria-hidden className="absolute top-7 right-[12.5%] left-[12.5%] hidden h-0.5 bg-gradient-to-r from-gold-400 via-brand-300 to-brand-700 lg:block" />
            <span aria-hidden className="absolute top-2 bottom-2 left-7 w-0.5 bg-gradient-to-b from-gold-400 via-brand-300 to-brand-700 lg:hidden" />
            {[1, 2, 3, 4].map((n, i) => (
              <Reveal as="li" key={n} delay={i * 0.07} className="relative flex gap-5 lg:flex-col lg:items-center lg:text-center">
                <span className={cn('relative z-10 grid size-14 shrink-0 place-items-center rounded-full font-display text-xl font-black ring-8 ring-white', n === 4 ? 'bg-brand-800 text-gold-400' : 'bg-gold-400 text-brand-900')}>{n}</span>
                <div className="lg:mt-5">
                  <h3 className="text-lg font-extrabold">{t(`about.method.${n}` as MessageKey)}</h3>
                  <p className="mt-2 text-muted">{t(`about.method.${n}.text` as MessageKey)}</p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* 8. Trainers — CMS team, category «teacher» only (never management) */}
      {trainers.length ? (
        <section id="trainers" className="section scroll-mt-24 bg-surface-purple">
          <div className="container-page">
            <SectionHeader title={t('about.team.title')} text={t('about.team.text')} link={{ to: '/team', label: t('cta.allTeam') }} />
            <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {trainers.slice(0, 4).map((member, i) => (
                <Reveal as="li" key={member.id} delay={i * 0.05}><TeamCard member={member} /></Reveal>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {/* 7. Gallery — real photos from news, achievements and events */}
      {gallery.length >= 3 ? (
        <section className="section">
          <div className="container-page">
            <SectionHeader title={t('about.gallery.title')} text={t('about.gallery.text')} link={{ to: '/projects', label: t('about.hero.projects') }} />
            <Gallery photos={gallery} title={t('about.gallery.title')} />
          </div>
        </section>
      ) : null}

      {/* 9. Why parents choose us */}
      <section className="section bg-brand-800 text-white">
        <div className="container-page">
          <Reveal className="mb-10 max-w-2xl sm:mb-12">
            <h2 className="text-section-title font-extrabold text-white">{t('about.why.title')}</h2>
            <p className="mt-4 text-base text-white/75 sm:text-lg">{t('about.why.text')}</p>
          </Reveal>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:gap-5">
            {WHY.map(({ n, icon: Icon, to }, i) => {
              const detail = n === 6
                ? branch ? t('about.why.6.text', { address: clean(branch.address), hours: clean(branch.working_hours) }) : t('about.why.6.textNone')
                : t(`about.why.${n}.text` as MessageKey)
              const body = (
                <>
                  <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-gold-400 text-brand-900"><Icon className="size-6" aria-hidden /></span>
                  <span className="min-w-0">
                    <span className="block text-lg leading-snug font-extrabold text-white">{t(`about.why.${n}` as MessageKey)}</span>
                    <span className="mt-1.5 block text-[15px] leading-relaxed text-white/75">{detail}</span>
                  </span>
                </>
              )
              const box = 'flex h-full items-start gap-4 rounded-3xl border border-white/10 bg-white/[0.06] p-6'
              return (
                <Reveal as="li" key={n} delay={i * 0.04}>
                  {to ? (
                    to.startsWith('#') ? (
                      <a href={to} className={cn(box, 'transition hover:border-gold-400/60 hover:bg-white/10')}>{body}</a>
                    ) : (
                      <Link to={path(to)} className={cn(box, 'transition hover:border-gold-400/60 hover:bg-white/10')}>{body}</Link>
                    )
                  ) : (
                    <div className={box}>{body}</div>
                  )}
                </Reveal>
              )
            })}
          </ul>
        </div>
      </section>

      {/* 10. Testimonials — published, with consent (public CMS) */}
      {reviews.length ? (
        <section className="section">
          <div className="container-page">
            <SectionHeader
              title={t('about.testimonials.title')}
              text={testimonials.data?.average_rating ? (
                <span className="inline-flex flex-wrap items-center gap-2">
                  <Stars rating={Math.round(testimonials.data.average_rating)} />
                  {t('about.testimonials.summary', { rating: testimonials.data.average_rating, count: testimonials.data.count })}
                </span>
              ) : undefined}
              link={{ to: '/testimonials', label: t('cta.allTestimonials') }}
            />
            <ul className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {reviews.map((item, i) => (
                <Reveal as="li" key={item.id} delay={i * 0.05} className="[&_blockquote]:line-clamp-8"><TestimonialCard item={item} /></Reveal>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {/* 11. FAQ */}
      <section className="section bg-surface-soft">
        <div className="container-page grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <h2 className="text-section-title font-extrabold">{t('about.faq.title')}</h2>
          </Reveal>
          <div className="space-y-3">
            {faq.map(({ q, a }, i) => (
              <details key={i} className="group card overflow-hidden open:shadow-lift">
                <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 font-extrabold text-ink marker:hidden sm:px-6 [&::-webkit-details-marker]:hidden">
                  {q}
                  <ChevronDown className="size-5 shrink-0 text-brand-600 transition group-open:rotate-180" aria-hidden />
                </summary>
                <p className="px-5 pb-5 leading-relaxed text-ink-soft sm:px-6">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* 12. Final CTA — the existing enrollment flow */}
      <FinalCta title={t('about.cta.title')} text={t('about.cta.text')} ctaLabel={t('about.cta.button')} />
    </>
  )
}
