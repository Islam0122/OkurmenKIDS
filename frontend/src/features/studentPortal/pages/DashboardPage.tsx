import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Award, Bell, CalendarClock, CalendarX, CheckCircle2, ClipboardList, CreditCard, Flame, MessageSquareQuote, Sparkles, Star, Trophy } from 'lucide-react'
import { Link } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type { Achievement, FeedbackItem, PortalHomework, PortalNotification } from '@/types/studentPortal'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import type { TFunction } from '../i18n'
import { Bar, Empty, HomeworkBadge, LessonRow, LoadError, Loading, PCard, ProgressRing } from '../ui'

export function notificationText(t: TFunction, n: PortalNotification): string {
  const p = n.params
  if (n.kind === 'homework_due') return t(p.days_left === 0 ? 'notif.homework_due_today' : 'notif.homework_due', p)
  if (n.kind === 'homework_checked' && p.score !== null && p.score !== undefined) return t('notif.homework_checked_score', p)
  return t(`notif.${n.kind}`, p)
}

const NOTIF_ICON = {
  homework_not_submitted: { icon: AlertCircle, tone: 'text-danger bg-danger-soft' },
  homework_due: { icon: CalendarClock, tone: 'text-warning bg-warning-soft' },
  homework_new: { icon: ClipboardList, tone: 'text-info bg-info-soft' },
  homework_checked: { icon: CheckCircle2, tone: 'text-brand-700 bg-brand-50' },
  lesson_cancelled: { icon: CalendarX, tone: 'text-danger bg-danger-soft' },
  payment_due: { icon: CreditCard, tone: 'text-warning bg-warning-soft' },
} as const

export function NotificationList({ items }: { items: PortalNotification[] }) {
  const { t, date } = usePortalI18n()
  if (!items.length) return <Empty>{t('dash.noNotifications')}</Empty>
  return (
    <ul className="space-y-2">
      {items.map((n) => {
        const { icon: Icon, tone } = NOTIF_ICON[n.kind]
        const href = n.params.homework_id ? `/student/homework/${n.params.homework_id}` : n.kind === 'payment_due' ? '/student/payments' : '/student/schedule'
        return (
          <li key={n.id}>
            <Link to={href} className="flex items-start gap-3 rounded-xl p-2 hover:bg-surface-hover">
              <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-lg', tone)}><Icon className="size-4" aria-hidden /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-ink">{notificationText(t, n)}</span>
                <span className="text-xs text-ink-muted">{date(n.date)}</span>
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

export function achievementText(t: TFunction, month: (i: number) => string, a: Achievement) {
  if (a.code === 'perfect_attendance') return t('ach.perfect_attendance', { month: `${month(a.params.month)} ${a.params.year}` })
  return t(`ach.${a.code}`, a.params)
}

const ACH_ICON = { scholarship: Trophy, perfect_attendance: Flame, top_homework: Star, homework_streak: Award, level: Sparkles }

export function HomeworkMini({ hw }: { hw: PortalHomework }) {
  const { t, date } = usePortalI18n()
  return (
    <Link to={`/student/homework/${hw.id}`} className="flex items-center justify-between gap-3 rounded-xl border border-border/70 p-3 hover:border-brand-200 hover:bg-brand-50/40">
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-ink">{hw.title}</span>
        <span className="block truncate text-xs text-ink-secondary">
          {hw.subject?.name ? `${hw.subject.name} · ` : ''}
          {hw.deadline ? t('hw.deadline', { date: date(hw.deadline) }) : t('hw.noDeadline')}
          {hw.state === 'awaiting' && hw.days_left !== null && hw.days_left >= 0
            ? ` · ${hw.days_left === 0 ? t('hw.dueToday') : t('hw.daysLeft', { n: hw.days_left })}` : ''}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {hw.score !== null ? <span className="text-sm font-bold tabular-nums text-brand-700">{hw.score}/10</span> : null}
        <HomeworkBadge state={hw.state} />
      </span>
    </Link>
  )
}

export function FeedbackList({ items }: { items: FeedbackItem[] }) {
  const { t, date } = usePortalI18n()
  if (!items.length) return <Empty>{t('dash.noFeedback')}</Empty>
  return (
    <ul className="space-y-3">
      {items.map((item, i) => (
        <li key={i} className="rounded-xl bg-surface-muted p-3">
          <p className="text-sm text-ink">«{item.text}»</p>
          <p className="mt-1.5 text-xs text-ink-muted">
            {[item.teacher?.name, item.subject?.name, t(`feedback.${item.kind}`), date(item.date)].filter(Boolean).join(' · ')}
            {item.score !== null ? ` · ${item.score}/10` : ''}
          </p>
        </li>
      ))}
    </ul>
  )
}

export function StudentDashboardPage() {
  const { student, me } = usePortal()
  const { t, month } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'dashboard', student.id],
    queryFn: () => studentPortalApi.dashboard(student.id),
    ...LIVE_QUERY,
  })
  if (isPending) return <Loading />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />

  const { xp } = data
  return (
    <div className="space-y-5">
      <div className="overflow-hidden rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 p-5 text-white shadow-sm sm:p-6">
        <p className="text-sm text-white/80">{t('dash.hello')}</p>
        <h1 className="mt-0.5 text-2xl font-bold tracking-tight">{student.full_name}</h1>
        <p className="mt-1 text-sm text-white/80">{t('dash.subtitle', { group: student.group?.name ?? '—', course: student.course?.name ?? '' })}</p>
        <div className="mt-4 grid max-w-xl grid-cols-3 gap-2">
          {[
            [t('dash.attendance'), data.attendance.month.percent === null ? '—' : `${Math.round(data.attendance.month.percent)}%`],
            [t('dash.avgScore'), data.performance.average_score ?? '—'],
            ['XP', xp.total],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl bg-white/12 px-3 py-2 backdrop-blur">
              <p className="truncate text-[11px] text-white/75">{label}</p>
              <p className="text-lg font-bold tabular-nums">{value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <PCard title={t('dash.today')} className="lg:col-span-2"
          action={<Link to="/student/schedule" className="text-sm font-medium text-brand-700">{t('nav.schedule')}</Link>}>
          {data.today_lessons.length ? (
            <div className="space-y-2">{data.today_lessons.map((l) => <LessonRow key={l.id} lesson={l} />)}</div>
          ) : <Empty>{t('dash.noLessonsToday')}</Empty>}
          <h3 className="mb-2 mt-5 text-sm font-semibold text-ink-secondary">{t('dash.upcoming')}</h3>
          {data.upcoming_lessons.length ? (
            <div className="space-y-2">{data.upcoming_lessons.map((l) => <LessonRow key={l.id} lesson={l} showDate />)}</div>
          ) : <Empty>{t('dash.noUpcoming')}</Empty>}
        </PCard>

        <PCard title={<span className="inline-flex items-center gap-2"><Bell className="size-4 text-brand-600" aria-hidden />{t('dash.notifications')}</span>}>
          <NotificationList items={data.notifications} />
        </PCard>

        <PCard title={t('dash.homework')} className="lg:col-span-2"
          action={<Link to="/student/homework" className="text-sm font-medium text-brand-700">{t('dash.details')}</Link>}>
          <p className="mb-3 text-sm text-ink-secondary">
            {t('dash.openCount', { n: data.homework.open_count })}
            {data.homework.not_submitted_count ? <span className="text-danger"> · {t('dash.notSubmittedCount', { n: data.homework.not_submitted_count })}</span> : null}
          </p>
          {data.homework.open.length ? (
            <div className="grid gap-2 sm:grid-cols-2">{data.homework.open.map((hw) => <HomeworkMini key={hw.id} hw={hw} />)}</div>
          ) : <Empty>{t('dash.noOpenHomework')}</Empty>}
        </PCard>

        <PCard title={t('dash.attendance')} action={<Link to="/student/attendance" className="text-sm font-medium text-brand-700">{t('dash.details')}</Link>}>
          <div className="flex items-center gap-4">
            <ProgressRing value={data.attendance.month.percent} label={t('dash.attendance')} />
            <div className="space-y-1 text-sm">
              <p className="text-ink-secondary">{t('dash.thisMonth')}: <b className="text-ink">{data.attendance.month.attended}/{data.attendance.month.marked}</b></p>
              <p className="text-ink-secondary">{t('dash.overall')}: <b className="text-ink">{data.attendance.overall.percent === null ? '—' : `${Math.round(data.attendance.overall.percent)}%`}</b></p>
            </div>
          </div>
        </PCard>

        <PCard title={t('dash.performance')}>
          <div className="space-y-4">
            <div>
              <div className="mb-1 flex justify-between text-sm"><span className="text-ink-secondary">{t('dash.avgScore')}</span><b className="tabular-nums text-ink">{data.performance.average_score ?? '—'} / 10</b></div>
              <Bar value={data.performance.average_score === null ? null : data.performance.average_score * 10} />
            </div>
            <div>
              <div className="mb-1 flex justify-between text-sm"><span className="text-ink-secondary">{t('dash.hwRate')}</span><b className="tabular-nums text-ink">{data.performance.homework_rate === null ? '—' : `${Math.round(data.performance.homework_rate)}%`}</b></div>
              <Bar value={data.performance.homework_rate} />
            </div>
          </div>
        </PCard>

        <PCard title={t('dash.xp')}>
          <div className="flex items-end justify-between">
            <div>
              <p className="text-3xl font-bold tabular-nums text-ink">{xp.total}<span className="ml-1 text-base font-semibold text-ink-secondary">XP</span></p>
              <p className="text-sm font-medium text-brand-700">{t('dash.level', { n: xp.level.level })}</p>
            </div>
            <p className="text-xs text-ink-muted">{t('dash.xpMonth', { n: xp.month.total })}</p>
          </div>
          <Bar value={xp.level.progress} className="mt-3" />
          <p className="mt-1.5 text-xs text-ink-muted">{t('dash.xpToNext', { n: xp.level.next - xp.total })}</p>
        </PCard>

        <PCard title={t('dash.achievements')}>
          {data.achievements.length ? (
            <ul className="flex flex-wrap gap-2">
              {data.achievements.map((a, i) => {
                const Icon = ACH_ICON[a.code]
                return (
                  <li key={i} className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700">
                    <Icon className="size-3.5" aria-hidden />{achievementText(t, month, a)}
                  </li>
                )
              })}
            </ul>
          ) : <Empty>{t('dash.noAchievements')}</Empty>}
        </PCard>

        <PCard title={<span className="inline-flex items-center gap-2"><MessageSquareQuote className="size-4 text-brand-600" aria-hidden />{t('dash.feedback')}</span>} className="lg:col-span-2">
          <FeedbackList items={data.feedback} />
        </PCard>

        {me.can_view_payments ? (
          <PCard title={t('dash.payments')} action={<Link to="/student/payments" className="text-sm font-medium text-brand-700">{t('dash.details')}</Link>}>
            {data.payments ? (
              data.payments.has_debt ? (
                <div>
                  <p className="text-sm text-ink-secondary">{t('dash.debt')}</p>
                  <p className="text-2xl font-bold tabular-nums text-warning">{data.payments.due_now !== '0.00' ? data.payments.due_now : data.payments.debt} {t('common.som')}</p>
                  <p className="mt-1 text-xs text-ink-muted">{t('dash.paid')}: {data.payments.paid} {t('common.som')}</p>
                </div>
              ) : (
                <p className="flex items-center gap-2 text-sm font-medium text-brand-700"><CheckCircle2 className="size-5" aria-hidden />{t('dash.allPaid')}</p>
              )
            ) : <Empty>{t('pay.noContracts')}</Empty>}
          </PCard>
        ) : null}
      </div>
    </div>
  )
}
