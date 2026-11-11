import { ArrowUpRight, Briefcase, MessageCircle, Users } from 'lucide-react'
import { useMemo, useState } from 'react'

import { TeamCard } from '@/components/cards/TeamCard'
import { TeamMemberDialog } from '@/components/cards/TeamMemberDialog'
import { ButtonLink } from '@/components/shared/Button'
import { FilterChips } from '@/components/shared/FilterChips'
import { PageHero } from '@/components/shared/PageHero'
import { Reveal } from '@/components/shared/Reveal'
import { SectionHeader } from '@/components/shared/SectionHeader'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, ErrorState } from '@/components/shared/States'
import { env } from '@/app/config/env'
import { Gallery } from '@/features/content/Gallery'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useAchievements, useEvents, useOpenVacancies, useTeam } from '@/hooks/queries'
import { useListParams } from '@/hooks/useListParams'
import { useI18n } from '@/i18n'
import type { ImageAsset, TeamGroup, TeamMember } from '@/types/api'
import { cn } from '@/utils/cn'
import { absoluteUrl, mediaUrl } from '@/utils/media'

/** Display order of departments; only those with published members are shown. */
const GROUPS: TeamGroup[] = ['management', 'it_trainers', 'english_trainers', 'soft_skills_trainers', 'administration']

export function TeamPage() {
  const { t } = useI18n()
  const team = useTeam()
  const members = useMemo(() => team.data?.results ?? [], [team.data])
  const { params, update } = useListParams(['group'])
  const [open, setOpen] = useState<TeamMember | null>(null)

  const present = GROUPS.filter((g) => members.some((m) => m.group === g))
  const group = present.includes(params.group as TeamGroup) ? (params.group as TeamGroup) : 'all'
  const shown = group === 'all' ? members : members.filter((m) => m.group === group)
  const chips = [
    { value: 'all', label: t('filter.all'), count: members.length },
    ...present.map((g) => ({ value: g, label: t(`team.group.${g}`), count: members.filter((m) => m.group === g).length })),
  ]

  return (
    <>
      <Seo
        title={t('team.heroTitle')}
        description={t('team.heroText')}
        jsonLd={[
          breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('team.heroTitle'), path: '/team' }]),
          ...(members.length
            ? [{
                '@context': 'https://schema.org',
                '@type': 'EducationalOrganization',
                name: 'Okurmen Kids Digital',
                url: absoluteUrl('/'),
                employee: members.map((m) => ({
                  '@type': 'Person',
                  name: m.name,
                  jobTitle: m.position,
                  ...(m.photo ? { image: absoluteUrl(mediaUrl(m.photo.url) ?? '') } : {}),
                })),
              }]
            : []),
        ]}
      />
      <PageHero compact title={t('team.heroTitle')} crumbs={[{ label: t('nav.team') }]}>
        <p className="mt-3 max-w-2xl font-display text-lg font-extrabold text-brand-700 sm:text-xl">{t('team.heroSubtitle')}</p>
        <p className="mt-2 max-w-2xl text-base text-ink-soft sm:text-lg">{t('team.heroText')}</p>
      </PageHero>

      <section className="container-page pt-8 pb-2 sm:pt-12">
        {team.isPending ? (
          <CardSkeletons count={3} aspect="aspect-[4/5]" />
        ) : team.isError ? (
          <ErrorState error={team.error} onRetry={() => team.refetch()} />
        ) : members.length ? (
          <>
            {present.length > 1 ? (
              <div className="mb-8"><FilterChips chips={chips} value={group} onChange={(v) => update({ group: v })} label={t('team.heroTitle')} /></div>
            ) : null}
            <TeamGrid members={shown} onOpen={setOpen} />
          </>
        ) : (
          <TeamEmpty />
        )}
      </section>

      <TeamGallery />
      <JoinCta />
      <TeamMemberDialog member={open} onClose={() => setOpen(null)} />
    </>
  )
}

/**
 * Layout follows the number of people, so a small team never looks unfinished:
 * 1 → a centred horizontal profile card; 2 → two balanced columns;
 * 3+ → three per row on desktop, and an incomplete last row is centred.
 */
function TeamGrid({ members, onOpen }: { members: TeamMember[]; onOpen: (member: TeamMember) => void }) {
  if (members.length === 1) {
    const [member] = members
    return (
      <Reveal className="mx-auto max-w-3xl">
        <TeamCard member={member} layout="horizontal" onOpen={() => onOpen(member)} />
      </Reveal>
    )
  }
  const item = members.length === 2 ? 'w-full sm:w-[calc(50%-0.75rem)]' : 'w-full sm:w-[calc(50%-0.75rem)] lg:w-[calc(33.333%-1rem)]'
  return (
    <ul className={cn('mx-auto flex flex-wrap justify-center gap-6', members.length === 2 && 'max-w-4xl')}>
      {members.map((member, i) => (
        <Reveal as="li" key={member.id} delay={Math.min(i, 6) * 0.06} className={item}>
          <TeamCard member={member} onOpen={() => onOpen(member)} />
        </Reveal>
      ))}
    </ul>
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
  // 3 photos = one row; 6 = a large photo + 5 (three full rows). No half-empty rows.
  const shown = photos.slice(0, photos.length >= 6 ? 6 : 3)
  return (
    <section className="bg-surface-soft py-12 sm:py-16">
      <div className="container-page">
        <SectionHeader title={t('team.gallery.title')} text={t('team.gallery.text')}/>
        <Gallery photos={shown} title={t('team.gallery.title')} />
      </div>
    </section>
  )
}

/** Compact CTA: the existing careers site (apps.recruitment) when configured, otherwise enrollment. */
function JoinCta() {
  const { t } = useI18n()
  const careers = env.careersUrl
  const vacancies = useOpenVacancies(Boolean(careers))
  const open = vacancies.data?.count ?? 0
  // The join CTA only while the recruitment API answers; otherwise the enrollment CTA.
  const recruiting = Boolean(careers) && !vacancies.isError
  return (
    <section className="container-page py-10 sm:py-12">
      <Reveal>
        <div className="flex flex-col gap-5 rounded-3xl bg-brand-800 px-6 py-7 text-white sm:px-8 md:flex-row md:items-center md:justify-between lg:px-10">
          <div className="flex gap-4">
            <span className="hidden size-12 shrink-0 place-items-center rounded-2xl bg-gold-400 text-brand-900 sm:grid"><Briefcase className="size-6" aria-hidden /></span>
            <div>
              <h2 className="text-2xl font-black text-white sm:text-[1.75rem]">{recruiting ? t('team.join.title') : t('home.cta.title')}</h2>
              <p className="mt-1.5 max-w-xl text-white/80">{recruiting ? t('team.join.text') : t('home.cta.text')}</p>
              {recruiting && open > 0 ? <p className="mt-2 text-sm font-bold text-gold-300">{t('team.join.open', { count: open })}</p> : null}
            </div>
          </div>
          {recruiting ? (
            <ButtonLink to={careers} size="lg" className="w-full md:w-auto">{t('team.join.cta')} <ArrowUpRight className="size-5" aria-hidden /></ButtonLink>
          ) : (
            <EnrollButton size="lg" className="w-full md:w-auto" />
          )}
        </div>
      </Reveal>
    </section>
  )
}
