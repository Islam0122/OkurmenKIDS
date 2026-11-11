import { ArrowLeft, Award, Briefcase, Globe2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { specializationTags, TeamCard, TeamPhoto } from '@/components/cards/TeamCard'
import { Reveal } from '@/components/shared/Reveal'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { ErrorState, NotFoundState, PageSkeleton } from '@/components/shared/States'
import { RichText } from '@/features/content/RichText'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { isNotFound, useTeamMember } from '@/hooks/queries'
import { LANG_SHORT, LANGS, useI18n, type MessageKey } from '@/i18n'
import type { TeamMemberDetail } from '@/types/api'
import { excerpt } from '@/utils/format'
import { absoluteUrl, mediaUrl } from '@/utils/media'

/** /team/:slug — the public profile of one team member (GET /api/v1/public/site/team/<slug>/). */
export function TeamMemberPage() {
  const { slug = '' } = useParams()
  const { data, isPending, isError, error, refetch } = useTeamMember(slug)
  if (isPending) return <PageSkeleton />
  if (isError) return isNotFound(error) ? <NotFoundState /> : <div className="container-page section"><ErrorState error={error} onRetry={() => refetch()} /></div>
  return <Profile member={data} />
}

function Profile({ member }: { member: TeamMemberDetail }) {
  const { t, path, lang } = useI18n()
  const tags = specializationTags(member.specialization)
  const positions = LANGS.map((code) => ({ code, value: member.positions?.[code] ?? (code === lang ? member.position : null) }))
    .filter((p): p is { code: typeof p.code; value: string } => Boolean(p.value))
  const department = member.group ? t(`team.section.${member.group}` as MessageKey) : null

  return (
    <>
      <Seo
        title={`${member.name} — ${member.position}`}
        description={member.bio ? excerpt(member.bio) : member.position}
        image={member.photo?.url}
        type="article"
        jsonLd={[
          breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('nav.team'), path: '/team' }, { name: member.name, path: `/team/${member.slug}` }]),
          {
            '@context': 'https://schema.org',
            '@type': 'Person',
            name: member.name,
            jobTitle: member.position,
            url: absoluteUrl(path(`/team/${member.slug}`)),
            worksFor: { '@type': 'EducationalOrganization', name: 'Okurmen Kids Digital', url: absoluteUrl('/') },
            ...(member.photo ? { image: absoluteUrl(mediaUrl(member.photo.url) ?? '') } : {}),
            ...(tags.length ? { knowsAbout: tags } : {}),
          },
        ]}
      />

      {/* Editorial header: portrait + identity */}
      <section className="relative overflow-hidden bg-surface-purple">
        <div aria-hidden className="pointer-events-none absolute -top-24 -right-24 size-80 rounded-full bg-gold-200/40 blur-3xl" />
        <div className="container-page relative grid gap-8 py-8 sm:py-10 md:grid-cols-[minmax(0,20rem)_1fr] md:items-center md:gap-12 lg:grid-cols-[minmax(0,24rem)_1fr] lg:py-14">
          <div>
            <Link to={path('/team')} className="mb-5 inline-flex items-center gap-1.5 text-sm font-bold text-brand-700 hover:text-brand-900 md:hidden">
              <ArrowLeft className="size-4" aria-hidden /> {t('team.profile.back')}
            </Link>
            <div className="mx-auto aspect-[4/5] w-full max-w-xs overflow-hidden rounded-[2rem] bg-gradient-to-b from-white to-brand-50 shadow-lift ring-8 ring-white md:max-w-none">
              <TeamPhoto member={member} priority sizes="(min-width: 768px) 384px, 320px" className="size-full object-top" />
            </div>
          </div>
          <div>
            <Link to={path('/team')} className="mb-6 hidden items-center gap-1.5 text-sm font-bold text-brand-700 hover:text-brand-900 md:inline-flex">
              <ArrowLeft className="size-4" aria-hidden /> {t('team.profile.back')}
            </Link>
            {department ? <p className="mb-3 text-sm font-bold tracking-wide text-gold-600 uppercase">{department}</p> : null}
            <h1 className="text-4xl leading-[1.05] font-black sm:text-5xl">{member.name}</h1>
            <p className="mt-3 text-lg font-bold text-brand-600 sm:text-xl">{member.position}</p>

            {positions.length > 1 ? (
              <dl className="mt-6 grid gap-2 rounded-2xl bg-white/80 p-4 shadow-soft backdrop-blur sm:p-5">
                <dt className="mb-1 flex items-center gap-2 text-xs font-bold tracking-wide text-muted uppercase"><Globe2 className="size-4" aria-hidden />{t('team.profile.positions')}</dt>
                {positions.map((p) => (
                  <dd key={p.code} lang={p.code} className="flex gap-3 text-[15px]">
                    <span className="w-8 shrink-0 font-bold text-gold-600">{LANG_SHORT[p.code]}</span>
                    <span className="font-semibold text-ink">{p.value}</span>
                  </dd>
                ))}
              </dl>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3">
              {member.experience_years ? (
                <p className="flex items-center gap-2 text-sm font-bold text-ink-soft">
                  <Briefcase className="size-4 text-gold-500" aria-hidden />
                  {t('team.profile.experience')}: {t('team.years', { count: member.experience_years })}
                </p>
              ) : null}
            </div>
            {tags.length ? (
              <ul className="mt-4 flex flex-wrap gap-2" aria-label={t('team.profile.skills')}>
                {tags.map((tag) => <li key={tag} className="rounded-full border border-brand-100 bg-white px-3 py-1 text-sm font-bold text-brand-700">{tag}</li>)}
              </ul>
            ) : null}
          </div>
        </div>
      </section>

      {/* Biography, career, programs */}
      <div className="container-page grid gap-10 py-10 sm:py-14 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-14">
        <div className="min-w-0 space-y-12">
          {member.bio ? (
            <section>
              <h2 className="mb-4 text-2xl font-black sm:text-3xl">{t('team.profile.about')}</h2>
              <RichText source={member.bio} />
            </section>
          ) : null}

          {member.career.length ? (
            <section>
              <h2 className="mb-5 text-2xl font-black sm:text-3xl">{t('team.profile.career')}</h2>
              <ol className="relative space-y-5 border-l-2 border-brand-100 pl-6">
                {member.career.map((line, i) => {
                  const [period, ...rest] = line.split(':')
                  const hasPeriod = rest.length > 0 && /\d/.test(period)
                  return (
                    <Reveal as="li" key={i} delay={i * 0.04} className="relative">
                      <span className="absolute top-1.5 -left-[1.95rem] size-3.5 rounded-full border-[3px] border-white bg-gold-400 ring-2 ring-gold-200" aria-hidden />
                      {hasPeriod ? <p className="text-sm font-bold text-gold-600">{period.trim()}</p> : null}
                      <p className="font-semibold text-ink">{hasPeriod ? rest.join(':').trim() : line}</p>
                    </Reveal>
                  )
                })}
              </ol>
            </section>
          ) : null}

          {member.achievements.length ? (
            <section>
              <h2 className="mb-5 text-2xl font-black sm:text-3xl">{t('team.profile.achievements')}</h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {member.achievements.map((line, i) => (
                  <Reveal as="li" key={i} delay={i * 0.04} className="flex items-start gap-3 rounded-2xl bg-surface-purple p-4">
                    <Award className="mt-0.5 size-5 shrink-0 text-gold-500" aria-hidden />
                    <span className="font-semibold text-ink-soft">{line}</span>
                  </Reveal>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-3xl bg-brand-800 p-6 text-white">
            <p className="font-display text-xl font-black text-white">{t('home.cta.title')}</p>
            <p className="mt-2 text-sm text-white/80">{t('home.cta.text')}</p>
            <EnrollButton className="mt-5 w-full" />
          </div>
        </aside>
      </div>

      {member.colleagues.length ? (
        <section className="border-t border-line bg-surface-soft py-12 sm:py-14">
          <div className="container-page">
            <h2 className="mb-8 text-2xl font-black sm:text-3xl">{t('team.profile.colleagues')}</h2>
            <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {member.colleagues.map((c) => <li key={c.id} className="min-w-0"><TeamCard member={c} /></li>)}
            </ul>
          </div>
        </section>
      ) : null}
    </>
  )
}
