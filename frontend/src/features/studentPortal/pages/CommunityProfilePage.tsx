import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Heart, Newspaper, Rocket, Trophy } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { communityApi } from '@/api/community'
import type { Achievement } from '@/types/studentPortal'

import { usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { Empty, LoadError, Skeleton } from '../ui'
import { ACH_ICON, achievementText } from './DashboardPage'
import { AuthorAvatar, COMMUNITY_KEY, PostCard, useNoIndex } from './CommunityPage'

/** A student's community card: name, group, photo, badges, publications and
 * projects — nothing private (no contacts, birth date, payments or grades). */
export function StudentCommunityProfilePage() {
  useNoIndex()
  const { id } = useParams<{ id: string }>()
  const otherId = Number(id)
  const { student } = usePortal()
  const { t, month } = usePortalI18n()
  const query = useQuery({
    queryKey: [...COMMUNITY_KEY, student.id, 'profile', otherId],
    queryFn: () => communityApi.profile(student.id, otherId),
    retry: false,
  })

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/student/community" className="sp-press mb-4 inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-semibold text-ink-secondary hover:text-brand-700">
        <ArrowLeft className="size-4" aria-hidden />{t('cm.back')}
      </Link>
      {query.isPending ? <Skeleton className="h-56 w-full rounded-3xl" /> : null}
      {query.isError ? (
        (query.error as { response?: { status?: number } }).response?.status === 404
          ? <Empty illustration title={t('cm.empty.title')} />
          : <LoadError onRetry={() => void query.refetch()} />
      ) : null}
      {query.data ? (
        <div className="space-y-5">
          <section className="sp-card sp-rise overflow-hidden">
            <div className="h-24 bg-gradient-to-r from-brand-500 via-emerald-500 to-teal-500 sm:h-28" />
            <div className="-mt-10 flex flex-col items-center px-5 pb-5 text-center sm:-mt-12">
              <AuthorAvatar author={{ type: 'student', name: query.data.name, photo: query.data.photo }} size="lg" />
              <h1 className="mt-3 text-2xl font-extrabold tracking-tight text-ink">{query.data.name}</h1>
              {query.data.group ? <p className="mt-1 text-sm text-ink-secondary">{query.data.group.name}</p> : null}
              <dl className="mt-5 grid w-full max-w-sm grid-cols-3 gap-2">
                {[
                  { icon: Newspaper, label: t('cm.profile.posts'), value: query.data.posts_count },
                  { icon: Heart, label: t('cm.profile.likes'), value: query.data.likes_received },
                  { icon: Rocket, label: t('cm.profile.projects'), value: query.data.projects.length },
                ].map(({ icon: Icon, label, value }) => (
                  <div key={label} className="rounded-2xl bg-surface-muted px-2 py-3">
                    <Icon className="mx-auto size-4 text-brand-600" aria-hidden />
                    <dd className="mt-1 text-xl font-bold tabular-nums text-ink">{value}</dd>
                    <dt className="text-xs text-ink-muted">{label}</dt>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          <section className="sp-card p-5">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-bold text-ink"><Trophy className="size-4 text-brand-600" aria-hidden />{t('cm.profile.badges')}</h2>
            {query.data.badges.length ? (
              <ul className="flex flex-wrap gap-2">
                {query.data.badges.map((badge, i) => {
                  const Icon = ACH_ICON[badge.code as keyof typeof ACH_ICON] ?? Trophy
                  return (
                    <li key={`${badge.code}-${i}`} className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-800">
                      <Icon className="size-4" aria-hidden />{achievementText(t, month, badge as unknown as Achievement)}
                    </li>
                  )
                })}
              </ul>
            ) : <p className="text-sm text-ink-muted">{t('cm.profile.noBadges')}</p>}
          </section>

          <section>
            <h2 className="mb-3 flex items-center gap-2 px-1 text-sm font-bold text-ink"><Rocket className="size-4 text-brand-600" aria-hidden />{t('cm.profile.projects')}</h2>
            {query.data.projects.length ? (
              <div className="space-y-4">{query.data.projects.map((post) => <PostCard key={post.id} post={post} />)}</div>
            ) : <Empty>{t('cm.profile.noProjects')}</Empty>}
          </section>
        </div>
      ) : null}
    </div>
  )
}
