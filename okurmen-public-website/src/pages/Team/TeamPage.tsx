import { ArrowRight, ArrowUpRight, BookOpen, Briefcase, MessageCircle, Users } from 'lucide-react'
import { useMemo } from 'react'

import { env } from '@/app/config/env'
import { TeamCard } from '@/components/cards/TeamCard'
import { ButtonLink } from '@/components/shared/Button'
import { PageHero } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { crumbsLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, ErrorState } from '@/components/shared/States'
import { Gallery } from '@/features/content/Gallery'
import { useAchievements, useEvents, useOpenVacancies, useTeam } from '@/hooks/queries'
import { useI18n, type MessageKey } from '@/i18n'
import type { ImageAsset, TeamCategory, TeamGroup, TeamMember } from '@/types/api'
import { cn } from '@/utils/cn'
import { absoluteUrl, mediaUrl } from '@/utils/media'
import { teamCategory } from '@/utils/team'
import { BRAND } from '@/app/config/site'

/** Teaching departments in page order; teachers without a department come last. */
const TEACHER_GROUPS: TeamGroup[] = ['it_trainers', 'soft_skills_trainers', 'english_trainers']

/** Public categories in page order — every profile is in exactly one (CMS field `category`). */
const CATEGORIES: TeamCategory[] = ['management', 'teacher', 'staff']

interface Department {
  key: TeamGroup | 'other'
  members: TeamMember[]
}

interface Section {
  key: TeamCategory
  members: TeamMember[]
  /** Teachers only: split by department when more than one is filled. */
  departments: Department[]
}

function teacherDepartments(members: TeamMember[]): Department[] {
  const list: Department[] = TEACHER_GROUPS.map((key) => ({ key, members: members.filter((m) => m.group === key) }))
  list.push({ key: 'other', members: members.filter((m) => !m.group || !TEACHER_GROUPS.includes(m.group)) })
  const filled = list.filter((d) => d.members.length)
  return filled.length > 1 ? filled : []
}

export function TeamPage() {
  const { t, path, lang } = useI18n()
  const team = useTeam()
  const members = useMemo(() => team.data?.results ?? [], [team.data])
  const sections = useMemo<Section[]>(() => CATEGORIES
    .map((key) => {
      const list = members.filter((m) => teamCategory(m) === key)
      return { key, members: list, departments: key === 'teacher' ? teacherDepartments(list) : [] }
    })
    .filter((s) => s.members.length), [members])

  return (
    <>
      <Seo
        page="/team"
        jsonLd={[
          crumbsLd(lang, 'team'),
          ...(members.length
            ? [{
                '@context': 'https://schema.org',
                '@type': 'EducationalOrganization',
                '@id': absoluteUrl('/#organization'),
                name: BRAND.name,
                url: absoluteUrl('/'),
                employee: members.map((m) => ({
                  '@type': 'Person',
                  name: m.name,
                  jobTitle: m.position,
                  url: absoluteUrl(path(`/team/${m.slug}`)),
                  ...(m.photo ? { image: absoluteUrl(mediaUrl(m.photo.url) ?? '') } : {}),
                })),
              }]
            : []),
        ]}
      />
      <PageHero compact title={t('team.heroTitle')} text={t('team.heroText')} crumbs={[{ label: t('nav.team') }]} />

      {team.isPending ? (
        <div className="container-page py-10"><CardSkeletons count={3} aspect="aspect-[4/5]" /></div>
      ) : team.isError ? (
        <div className="container-page py-10"><ErrorState error={team.error} onRetry={() => team.refetch()} /></div>
      ) : sections.length ? (
        sections.map((section, index) => <TeamSection key={section.key} section={section} index={index} />)
      ) : (
        <div className="container-page py-10"><TeamEmpty /></div>
      )}

      <TeamGallery />
      <TeamCta />
    </>
  )
}

/**
 * «Руководство академии» on a soft purple band with wide professional cards;
 * «Наши преподаватели» (and staff) on white with a 3-column grid of teacher cards.
 */
function TeamSection({ section, index }: { section: Section; index: number }) {
  const { t } = useI18n()
  const lead = section.key === 'management'
  const number = String(index + 1).padStart(2, '0')
  const grid = (members: TeamMember[]) => (
    <ul className={cn('grid gap-6', lead ? 'lg:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-3')}>
      {members.map((member, i) => (
        <Reveal as="li" key={member.id} delay={Math.min(i, 6) * 0.06} className="min-w-0">
          <TeamCard member={member} variant={lead ? 'lead' : 'default'} />
        </Reveal>
      ))}
    </ul>
  )
  return (
    <section aria-labelledby={`team-${section.key}`} className={cn(lead ? 'bg-surface-purple/70' : index > 0 && 'border-t border-line', 'py-12 sm:py-14')}>
      <div className="container-page">
        <Reveal className="mb-8 flex flex-col gap-3 sm:mb-10 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl">
            <p className="mb-3 flex items-center gap-2 text-sm font-bold text-gold-600">
              <span className="font-display tabular-nums">{number}</span>
              <span className="h-px w-8 bg-gold-400" aria-hidden />
              <span className="flex items-center gap-1.5 text-muted"><Users className="size-4" aria-hidden />{section.members.length}</span>
            </p>
            <h2 id={`team-${section.key}`} className="text-section-title font-black">{t(`team.category.${section.key}` as MessageKey)}</h2>
            <p className="mt-2 text-base text-muted sm:text-lg">{t(`team.categoryText.${section.key}` as MessageKey)}</p>
          </div>
        </Reveal>
        {section.departments.length ? (
          <div className="space-y-10">
            {section.departments.map((d) => (
              <div key={d.key} aria-labelledby={`team-${section.key}-${d.key}`} role="group">
                <h3 id={`team-${section.key}-${d.key}`} className="mb-5 flex items-center gap-3 font-display text-xl font-extrabold text-brand-800">
                  <span className="h-5 w-1 rounded-full bg-gold-400" aria-hidden />
                  {t(`team.section.${d.key}` as MessageKey)}
                </h3>
                {grid(d.members)}
              </div>
            ))}
          </div>
        ) : grid(section.members)}
      </div>
    </section>
  )
}

function TeamEmpty() {
  const { t } = useI18n()
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-4 rounded-3xl border border-line bg-surface-soft px-6 py-8 text-center sm:flex-row sm:text-left">
      <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-white text-brand-500 shadow-soft"><Users className="size-7" aria-hidden /></span>
      <div className="flex-1">
        <p className="font-display text-lg font-extrabold">{t('team.empty.title')}</p>
        <p className="mt-1 text-sm text-muted">{t('team.empty.text')}</p>
      </div>
      <ButtonLink to="/contacts" size="sm" variant="outline"><MessageCircle className="size-4" aria-hidden />{t('cta.contactUs')}</ButtonLink>
    </div>
  )
}

/** «Team in action»: real photos already published on the site (event and achievement covers). Hidden with fewer than 3. */
function TeamGallery() {
  const { t } = useI18n()
  const events = useEvents({ phase: 'completed', page_size: 6 })
  const achievements = useAchievements({ page_size: 6 })
  const photos = [...(events.data?.results ?? []).map((e) => e.cover), ...(achievements.data?.results ?? []).map((a) => a.cover)]
    .filter((p): p is ImageAsset => Boolean(p))
  if (photos.length < 3) return null
  const shown = photos.slice(0, photos.length >= 6 ? 6 : 3)
  return (
    <section className="border-t border-line bg-surface-soft py-12 sm:py-14">
      <div className="container-page">
        <SectionHeader title={t('team.gallery.title')} text={t('team.gallery.text')} />
        <Gallery photos={shown} title={t('team.gallery.title')} />
      </div>
    </section>
  )
}

/** Recruitment only while there are open vacancies (apps.recruitment); otherwise invite parents to the academy. */
function TeamCta() {
  const { t } = useI18n()
  const careers = env.careersUrl
  const vacancies = useOpenVacancies(Boolean(careers))
  const open = vacancies.data?.count ?? 0
  const recruiting = Boolean(careers) && open > 0
  return (
    <section className="container-page py-10 sm:py-12">
      <Reveal>
        <div className="flex flex-col gap-5 rounded-3xl bg-brand-800 px-6 py-7 text-white sm:px-8 lg:flex-row lg:items-center lg:justify-between lg:px-10">
          <div className="flex gap-4">
            <span className="hidden size-12 shrink-0 place-items-center rounded-2xl bg-gold-400 text-brand-900 sm:grid">
              {recruiting ? <Briefcase className="size-6" aria-hidden /> : <BookOpen className="size-6" aria-hidden />}
            </span>
            <div>
              <h2 className="text-2xl font-black text-white sm:text-[1.75rem]">{recruiting ? t('team.join.title') : t('team.discover.title')}</h2>
              <p className="mt-1.5 max-w-xl text-white/80">{recruiting ? t('team.join.text') : t('team.discover.text')}</p>
              {recruiting ? <p className="mt-2 text-sm font-bold text-gold-300">{t('team.join.open', { count: open })}</p> : null}
            </div>
          </div>
          {recruiting ? (
            <ButtonLink to={careers} size="lg" className="w-full sm:w-auto">{t('team.join.cta')} <ArrowUpRight className="size-5" aria-hidden /></ButtonLink>
          ) : (
            <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
              <ButtonLink to="/courses" size="lg">{t('cta.courses')} <ArrowRight className="size-5" aria-hidden /></ButtonLink>
              <ButtonLink to="/about" size="lg" variant="light">{t('nav.about')}</ButtonLink>
            </div>
          )}
        </div>
      </Reveal>
    </section>
  )
}
