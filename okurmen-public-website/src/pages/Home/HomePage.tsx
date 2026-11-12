import type { ReactNode } from 'react'

import { AchievementCard } from '@/components/cards/AchievementCard'
import { EventCard } from '@/components/cards/EventCard'
import { NewsCard } from '@/components/cards/NewsCard'
import { ProjectCard } from '@/components/cards/ProjectCard'
import { TeamCard } from '@/components/cards/TeamCard'
import { TestimonialCard } from '@/components/cards/TestimonialCard'
import { Banners } from '@/components/sections/Banners'
import { CardGrid } from '@/components/sections/CardGrid'
import { Hero } from '@/components/sections/Hero'
import { ProgramsSection } from '@/components/home/ProgramsSection'
import { RocketCta } from '@/components/home/RocketCta'
import { IntroVideo } from '@/components/sections/IntroVideo'
import { Stats } from '@/components/sections/Stats'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { organizationLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, ErrorState } from '@/components/shared/States'
import { useHome } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { HomeData, SectionKey } from '@/types/api'
import { cn } from '@/utils/cn'

/** The redesigned showcase blocks (projects, achievements, news): 1280 px wide, optional light-purple panel. */
function Showcase({ children, panel }: { children: ReactNode; panel?: boolean }) {
  return (
    <section className="py-6 sm:py-8 lg:py-10">
      <div className="mx-auto w-full max-w-[1280px] px-4 sm:px-6 lg:px-8">
        <div className={cn(panel && 'rounded-[2rem] bg-kids-bg px-4 py-8 sm:px-8 sm:py-10 lg:px-10')}>{children}</div>
      </div>
    </section>
  )
}

/** The homepage shows three cards per showcase block (the full lists are one click away). */
const SHOWCASE = 3

/** Sections in the order and visibility set in the CMS («Главная страница»). Empty ones are skipped. */
function renderSection(key: SectionKey, data: HomeData, title: string, t: ReturnType<typeof useI18n>['t']): ReactNode {
  switch (key) {
    case 'video':
      return <IntroVideo key={key} src={data.intro_video} title={title} />
    case 'stats':
      return <Stats key={key} stats={data.stats} title={title} />
    case 'courses':
      // The six directions are always shown; a published CMS course adds its page, age and tagline.
      return <ProgramsSection key={key} courses={data.courses} title={title} />
    case 'projects':
      return data.projects.length ? (
        <Showcase key={key} panel>
          <SectionHeader eyebrow={t('home.showcase.projects.eyebrow')} title={title || t('home.showcase.projects.title')} text={t('home.showcase.projects.text')} link={{ to: '/projects', label: t('cta.allProjects') }} />
          <CardGrid items={data.projects.slice(0, SHOWCASE)} keyOf={(p) => p.key} render={(p) => <ProjectCard project={p} />} scroll />
        </Showcase>
      ) : null
    case 'achievements':
      return data.achievements.length ? (
        <Showcase key={key}>
          <SectionHeader eyebrow={t('home.showcase.achievements.eyebrow')} title={title || t('home.showcase.achievements.title')} text={t('home.showcase.achievements.text')} link={{ to: '/achievements', label: t('cta.allAchievements') }} />
          <CardGrid items={data.achievements.slice(0, SHOWCASE)} keyOf={(a) => a.slug} render={(a) => <AchievementCard item={a} />} scroll />
        </Showcase>
      ) : null
    case 'news':
      return data.news.length ? (
        <Showcase key={key}>
          <SectionHeader eyebrow={t('home.showcase.news.eyebrow')} title={title || t('home.showcase.news.title')} link={{ to: '/news', label: t('cta.allNews') }} />
          <CardGrid items={data.news.slice(0, SHOWCASE)} keyOf={(n) => n.slug} render={(n) => <NewsCard item={n} readMore={t('home.showcase.news.read')} />} scroll />
        </Showcase>
      ) : null
    case 'events':
      return data.events.length ? (
        <Showcase key={key}>
          <SectionHeader eyebrow={t('nav.events')} title={title || t('home.events.title')} text={t('home.events.text')} link={{ to: '/events', label: t('cta.allEvents') }} />
          <CardGrid items={data.events.slice(0, SHOWCASE)} keyOf={(e) => e.slug} render={(e) => <EventCard event={e} />} scroll />
        </Showcase>
      ) : null
    case 'team':
      return data.team.length ? (
        <Showcase key={key} panel>
          <SectionHeader eyebrow={t('nav.team')} title={title || t('home.team.title')} text={t('home.team.text')} link={{ to: '/team', label: t('cta.allTeam') }} />
          <CardGrid items={data.team} keyOf={(m) => m.id} render={(m) => <TeamCard member={m} />} columns={4} scroll />
        </Showcase>
      ) : null
    case 'testimonials':
      return data.testimonials.length ? (
        <Showcase key={key}>
          <SectionHeader eyebrow={t('nav.testimonials')} title={title || t('home.testimonials.title')} link={{ to: '/testimonials', label: t('cta.allTestimonials') }} />
          <CardGrid items={data.testimonials.slice(0, SHOWCASE)} keyOf={(r) => r.id} render={(r) => <div className="h-full [&_blockquote]:line-clamp-8"><TestimonialCard item={r} /></div>} scroll />
        </Showcase>
      ) : null
    case 'cta':
      return <RocketCta key={key} title={title} />
  }
}

export function HomePage() {
  const { t } = useI18n()
  const { data, isPending, isError, error, refetch } = useHome()

  return (
    <>
      <Seo
        description={t('home.seo.description')}
        jsonLd={organizationLd({
          phone: data?.contacts.phone,
          email: data?.contacts.email,
          sameAs: [data?.contacts.instagram ?? null, data?.contacts.telegram ?? null],
          addresses: data?.branches.map((b) => b.address),
        })}
      />
      <Hero hero={data?.hero} programsHref={!data || data.sections.some((s) => s.key === 'courses') ? '#programs' : '/courses'} />
      {isPending ? (
        <div className="container-page section"><CardSkeletons /></div>
      ) : isError ? (
        <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
      ) : (
        <>
          <Banners banners={data.banners} />
          {data.sections.map((section) => renderSection(section.key, data, section.title, t))}
        </>
      )}
    </>
  )
}
