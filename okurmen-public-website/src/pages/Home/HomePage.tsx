import type { ReactNode } from 'react'

import { AchievementCard } from '@/components/cards/AchievementCard'
import { CourseCard } from '@/components/cards/CourseCard'
import { EventCard } from '@/components/cards/EventCard'
import { NewsCard } from '@/components/cards/NewsCard'
import { ProjectCard } from '@/components/cards/ProjectCard'
import { TeamCard } from '@/components/cards/TeamCard'
import { TestimonialCard } from '@/components/cards/TestimonialCard'
import { Banners } from '@/components/sections/Banners'
import { CardGrid } from '@/components/sections/CardGrid'
import { FinalCta } from '@/components/sections/FinalCta'
import { Hero } from '@/components/sections/Hero'
import { IntroVideo } from '@/components/sections/IntroVideo'
import { Stats } from '@/components/sections/Stats'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { organizationLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, ErrorState } from '@/components/shared/States'
import { useHome } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import type { HomeData, SectionKey } from '@/types/api'
import { cn } from '@/utils/cn'

function Block({ children, tinted }: { children: ReactNode; tinted?: boolean }) {
  return (
    <section className={cn('section', tinted && 'bg-surface-soft')}>
      <div className="container-page">{children}</div>
    </section>
  )
}

/** Sections in the order and visibility set in the CMS («Главная страница»). Empty ones are skipped. */
function renderSection(key: SectionKey, data: HomeData, title: string, t: ReturnType<typeof useI18n>['t'], index: number): ReactNode {
  const tinted = index % 2 === 1
  switch (key) {
    case 'video':
      return <IntroVideo key={key} src={data.intro_video} title={title} />
    case 'stats':
      return <Stats key={key} stats={data.stats} title={title} />
    case 'courses':
      return data.courses.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.courses')} title={title || t('home.courses.title')} text={t('home.courses.text')} link={{ to: '/courses', label: t('cta.allCourses') }} />
          <CardGrid items={data.courses} keyOf={(c) => c.slug} render={(c) => <CourseCard course={c} />} scroll />
        </Block>
      ) : null
    case 'projects':
      return data.projects.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.projects')} title={title || t('home.projects.title')} text={t('home.projects.text')} link={{ to: '/projects', label: t('cta.allProjects') }} />
          <CardGrid items={data.projects} keyOf={(p) => p.key} render={(p) => <ProjectCard project={p} />} scroll />
        </Block>
      ) : null
    case 'achievements':
      return data.achievements.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.achievements')} title={title || t('home.achievements.title')} text={t('home.achievements.text')} link={{ to: '/achievements', label: t('cta.allAchievements') }} />
          <CardGrid items={data.achievements} keyOf={(a) => a.slug} render={(a) => <AchievementCard item={a} />} scroll />
        </Block>
      ) : null
    case 'news':
      return data.news.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.news')} title={title || t('home.news.title')} link={{ to: '/news', label: t('cta.allNews') }} />
          <CardGrid items={data.news} keyOf={(n) => n.slug} render={(n) => <NewsCard item={n} />} scroll />
        </Block>
      ) : null
    case 'events':
      return data.events.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.events')} title={title || t('home.events.title')} text={t('home.events.text')} link={{ to: '/events', label: t('cta.allEvents') }} />
          <CardGrid items={data.events} keyOf={(e) => e.slug} render={(e) => <EventCard event={e} />} scroll />
        </Block>
      ) : null
    case 'team':
      return data.team.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.team')} title={title || t('home.team.title')} text={t('home.team.text')} link={{ to: '/team', label: t('cta.allTeam') }} />
          <CardGrid items={data.team} keyOf={(m) => m.id} render={(m) => <TeamCard member={m} />} columns={4} scroll />
        </Block>
      ) : null
    case 'testimonials':
      return data.testimonials.length ? (
        <Block key={key} tinted={tinted}>
          <SectionHeader eyebrow={t('nav.testimonials')} title={title || t('home.testimonials.title')} link={{ to: '/testimonials', label: t('cta.allTestimonials') }} />
          <CardGrid items={data.testimonials} keyOf={(r) => r.id} render={(r) => <TestimonialCard item={r} />} scroll />
        </Block>
      ) : null
    case 'cta':
      return <FinalCta key={key} title={title} />
  }
}

export function HomePage() {
  const { t } = useI18n()
  const { data, isPending, isError, error, refetch } = useHome()

  return (
    <>
      <Seo
        jsonLd={organizationLd({
          phone: data?.contacts.phone,
          email: data?.contacts.email,
          sameAs: [data?.contacts.instagram ?? null, data?.contacts.telegram ?? null],
          addresses: data?.branches.map((b) => b.address),
        })}
      />
      <Hero hero={data?.hero} />
      {isPending ? (
        <div className="container-page section"><CardSkeletons /></div>
      ) : isError ? (
        <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
      ) : (
        <>
          <Banners banners={data.banners} />
          {data.sections.map((section, index) => renderSection(section.key, data, section.title, t, index))}
        </>
      )}
    </>
  )
}
