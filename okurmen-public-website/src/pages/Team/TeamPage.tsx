import { TeamCard } from '@/components/cards/TeamCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { FinalCta } from '@/components/sections/FinalCta'
import { PageHero } from '@/components/shared/PageHero'
import { breadcrumbLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useTeam } from '@/hooks/queries'
import { useI18n } from '@/i18n'

export function TeamPage() {
  const { t } = useI18n()
  const { data, isPending, isError, error, refetch } = useTeam()
  const team = data?.results ?? []
  return (
    <>
      <Seo title={t('team.title')} description={t('team.subtitle')} jsonLd={breadcrumbLd([{ name: t('nav.home'), path: '/' }, { name: t('team.title'), path: '/team' }])} />
      <PageHero title={t('team.title')} text={t('team.subtitle')} crumbs={[{ label: t('nav.team') }]} />
      <section className="container-page section">
        {isPending ? <CardSkeletons count={4} className="lg:grid-cols-4" aspect="aspect-[4/5]" /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : team.length ? (
          <CardGrid items={team} keyOf={(m) => m.id} render={(m) => <TeamCard member={m} detailed />} columns={4} />
        ) : <EmptyState />}
      </section>
      <FinalCta />
    </>
  )
}
