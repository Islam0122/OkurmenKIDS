import { useQuery } from '@tanstack/react-query'
import { Award, BookOpenCheck, CalendarCheck2, Info, Sparkles, Star, Target, Zap } from 'lucide-react'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { ACH_ICON, achievementText } from './DashboardPage'
import { Bar, Empty, LoadError, Loading, PCard, PageTitle, ProgressRing, Stat } from '../ui'

const MILESTONE_ICON = { homework_streak: Award, top_homework: Star, level: Sparkles }

/** «Жетишкендиктер»: XP, level, earned badges and the next goals — every
 * number from the same records and rules as the public leaderboard and the
 * dashboard badges (backend: portal.services.data.achievements_overview). */
export function StudentAchievementsPage() {
  const { student } = usePortal()
  const { t, month, date } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'achievements', student.id],
    queryFn: () => studentPortalApi.achievements(student.id),
    ...LIVE_QUERY,
  })
  if (isPending) return <Loading />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  const { xp } = data

  return (
    <div>
      <PageTitle title={t('ach.title')} subtitle={t('ach.subtitle')} />
      <div className="grid gap-5 lg:grid-cols-3">
        <section className="sp-card sp-rise relative overflow-hidden p-6 lg:col-span-2">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
            <div className="relative">
              <ProgressRing value={xp.level.progress} size={132} stroke={11} label={t('dash.level', { n: xp.level.level })} />
              <span className="absolute inset-x-0 -bottom-2 mx-auto w-fit rounded-full bg-brand-600 px-3 py-1 text-xs font-extrabold text-white shadow-sm">
                {t('dash.level', { n: xp.level.level })}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-brand-600">{t('ach.xpTotal')}</p>
              <p className="text-5xl font-extrabold tabular-nums tracking-tight text-ink">{xp.total.total}<span className="ml-1.5 text-xl font-bold text-ink-muted">XP</span></p>
              <p className="mt-1 text-sm text-ink-secondary">{t('dash.xpToNext', { n: xp.level.next - xp.total.total })}</p>
              <Bar value={xp.level.progress} className="mt-3" />
            </div>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-2 sm:gap-3">
            <Stat icon={<CalendarCheck2 className="size-3.5 text-brand-600" aria-hidden />} label={t('report.xpAttendance')} value={`+${xp.total.attendance}`} />
            <Stat icon={<BookOpenCheck className="size-3.5 text-brand-600" aria-hidden />} label={t('report.xpHomework')} value={`+${xp.total.homework}`} />
            <Stat icon={<Target className="size-3.5 text-brand-600" aria-hidden />} label={t('report.xpTests')} value={`+${xp.total.tests}`} />
          </div>
        </section>

        <PCard title={t('ach.xpMonth')} icon={<Zap className="size-4" aria-hidden />}>
          <p className="text-4xl font-extrabold tabular-nums tracking-tight text-brand-700">+{xp.month.total}<span className="ml-1 text-base font-bold">XP</span></p>
          <ul className="mt-3 space-y-1.5 text-sm text-ink-secondary">
            <li className="flex justify-between"><span>{t('report.xpAttendance')}</span><b className="tabular-nums text-ink">+{xp.month.attendance}</b></li>
            <li className="flex justify-between"><span>{t('report.xpHomework')}</span><b className="tabular-nums text-ink">+{xp.month.homework}</b></li>
            <li className="flex justify-between"><span>{t('report.xpTests')}</span><b className="tabular-nums text-ink">+{xp.month.tests}</b></li>
          </ul>
          <p className="mt-4 flex gap-2 rounded-2xl bg-surface-muted p-3 text-xs leading-relaxed text-ink-secondary">
            <Info className="mt-0.5 size-3.5 shrink-0 text-brand-600" aria-hidden />
            <span><b className="text-ink">{t('ach.howXp')}.</b> {t('ach.howXpText')}</span>
          </p>
        </PCard>

        <PCard title={t('ach.earned')} icon={<Award className="size-4" aria-hidden />} className="lg:col-span-2">
          {data.earned.length ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {data.earned.map((a, i) => {
                const Icon = ACH_ICON[a.code]
                return (
                  <li key={i} className="sp-card sp-card-hover flex items-center gap-3.5 p-3.5" style={{ animationDelay: `${i * 40}ms` }}>
                    <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
                      <Icon className="size-6" aria-hidden />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-bold leading-snug text-ink">{achievementText(t, month, a)}</span>
                      {a.date ? <span className="text-xs text-ink-muted">{date(a.date, true)}</span> : null}
                    </span>
                  </li>
                )
              })}
            </ul>
          ) : <Empty illustration title={t('ach.none')} />}
        </PCard>

        <PCard title={t('ach.next')} icon={<Target className="size-4" aria-hidden />}>
          <ul className="space-y-4">
            {data.milestones.map((m) => {
              const Icon = MILESTONE_ICON[m.code]
              const done = m.target === null
              const percent = done ? 100 : Math.round((m.current / (m.target as number)) * 100)
              return (
                <li key={m.code}>
                  <div className="mb-1.5 flex items-center gap-2.5">
                    <span className={cn('flex size-8 items-center justify-center rounded-xl', done ? 'bg-brand-600 text-white' : 'bg-brand-50 text-brand-600')}>
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1 text-sm font-semibold text-ink">
                      {done ? t('ach.ms.done') : t(`ach.ms.${m.code}`, { target: m.target, ...(m.params ?? {}) })}
                    </span>
                    {!done ? <span className="text-xs font-bold tabular-nums text-ink-muted">{m.current}/{m.target}</span> : null}
                  </div>
                  <Bar value={percent} />
                </li>
              )
            })}
          </ul>
        </PCard>
      </div>
    </div>
  )
}
