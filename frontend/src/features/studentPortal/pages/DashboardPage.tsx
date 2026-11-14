import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle, ArrowRight, Award, Bell, BookOpenCheck, CalendarClock, CalendarDays, CalendarX, CheckCircle2, ClipboardList,
  CreditCard, Flame, GraduationCap, MapPin, MessageSquareQuote, Sparkles, Star, Trophy, UserCheck, Zap,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type { Achievement, FeedbackItem, PortalHomework, PortalLesson, PortalNotification } from '@/types/studentPortal'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import type { TFunction } from '../i18n'
import { Avatar, Bar, CARD_LINK, Empty, HomeworkBadge, HW_STYLE, LessonRow, LoadError, Loading, PCard, ProgressRing } from '../ui'

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
    <ul className="space-y-1">
      {items.map((n) => {
        const { icon: Icon, tone } = NOTIF_ICON[n.kind]
        const href = n.params.homework_id ? `/student/homework/${n.params.homework_id}` : n.kind === 'payment_due' ? '/student/payments' : '/student/schedule'
        return (
          <li key={n.id}>
            <Link to={href} className="sp-press flex items-start gap-3 rounded-xl p-2.5 hover:bg-surface-hover">
              <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-xl', tone)}><Icon className="size-[18px]" aria-hidden /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium leading-snug text-ink">{notificationText(t, n)}</span>
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

export const ACH_ICON = { scholarship: Trophy, perfect_attendance: Flame, top_homework: Star, homework_streak: Award, level: Sparkles }

/** Compact homework row (dashboard preview, history list). The colour bar on the left repeats the status. */
export function HomeworkMini({ hw }: { hw: PortalHomework }) {
  const { t, date } = usePortalI18n()
  return (
    <Link to={`/student/homework/${hw.id}`}
      className="sp-card sp-card-hover group relative flex items-center justify-between gap-3 overflow-hidden p-3.5 pl-5">
      <span className={cn('absolute inset-y-3 left-0 w-1 rounded-r-full', HW_STYLE[hw.state].dot)} aria-hidden />
      <span className="min-w-0">
        <span className="block truncate text-sm font-bold text-ink group-hover:text-brand-700">{hw.title}</span>
        <span className="mt-0.5 block truncate text-xs text-ink-secondary">
          {hw.lesson.lesson_number ? `${t('hw.nextLesson', { n: hw.lesson.lesson_number })} · ` : ''}
          {hw.subject?.name ? `${hw.subject.name} · ` : ''}
          {hw.deadline ? t('hw.deadline', { date: date(hw.deadline) }) : t('hw.noDeadline')}
          {hw.state === 'awaiting' && hw.days_left !== null && hw.days_left >= 0
            ? ` · ${hw.days_left === 0 ? t('hw.dueToday') : t('hw.daysLeft', { n: hw.days_left })}` : ''}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {hw.score !== null ? <span className="rounded-lg bg-brand-50 px-2 py-0.5 text-sm font-extrabold tabular-nums text-brand-700">{hw.score}/10</span> : null}
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
        <li key={i} className="relative rounded-2xl bg-surface-muted p-4 pl-5">
          <span className="absolute inset-y-4 left-0 w-1 rounded-r-full bg-brand-500" aria-hidden />
          <p className="text-sm leading-relaxed text-ink">«{item.text}»</p>
          <p className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-ink-muted">
            <span className="font-semibold text-ink-secondary">{item.teacher?.name}</span>
            {[item.subject?.name, t(`feedback.${item.kind}`), date(item.date)].filter(Boolean).map((part) => <span key={part}>· {part}</span>)}
            {item.score !== null ? <span className="rounded-md bg-brand-50 px-1.5 font-bold text-brand-700">{item.score}/10</span> : null}
          </p>
        </li>
      ))}
    </ul>
  )
}

function NextLessonCard({ lesson }: { lesson: PortalLesson | undefined }) {
  const { t, date, weekday } = usePortalI18n()
  if (!lesson) {
    return (
      <PCard title={t('dash.nextLesson')} icon={<CalendarDays className="size-4" aria-hidden />}>
        <Empty>{t('dash.noNextLesson')}</Empty>
      </PCard>
    )
  }
  const day = (new Date(`${lesson.date}T00:00:00`).getDay() + 6) % 7
  return (
    <PCard title={t('dash.nextLesson')} icon={<CalendarDays className="size-4" aria-hidden />}>
      <div className="flex items-center gap-4">
        <div className="flex w-[4.5rem] shrink-0 flex-col items-center rounded-2xl bg-brand-600 py-2.5 text-white shadow-sm">
          <span className="text-[11px] font-bold uppercase tracking-wide text-white/80">{weekday(day)}</span>
          <span className="text-2xl font-extrabold leading-tight tabular-nums">{date(lesson.date).slice(0, 2)}</span>
          <span className="text-[11px] font-semibold tabular-nums text-white/90">{lesson.start}</span>
        </div>
        <div className="min-w-0">
          <p className="truncate text-lg font-extrabold tracking-tight text-ink">{lesson.subject?.name ?? lesson.course?.name}</p>
          <p className="truncate text-sm text-ink-secondary">
            {lesson.lesson_number ? `${t('hw.lessonNo', { n: lesson.lesson_number })} · ` : ''}{lesson.topic}
          </p>
          <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-ink-muted">
            <span className="whitespace-nowrap">{weekday(day, true)}, {date(lesson.date, true)}</span>
            <span className="whitespace-nowrap">{lesson.start}–{lesson.end}</span>
            {lesson.room || lesson.branch ? (
              <span className="inline-flex items-center gap-1"><MapPin className="size-3" aria-hidden />
                {[lesson.branch?.name, lesson.room ? t('lesson.room', { room: lesson.room.name }) : null].filter(Boolean).join(' · ')}
              </span>
            ) : null}
          </p>
        </div>
      </div>
    </PCard>
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

  const { xp, course_progress: progress } = data
  const nextLesson = data.today_lessons.find((l) => l.status === 'scheduled' || l.status === 'in_progress') ?? data.upcoming_lessons[0]
  const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v)}%`)

  return (
    <div className="space-y-5">
      {/* Welcome */}
      <section className="sp-card sp-rise relative overflow-hidden p-5 sm:p-7">
        <svg className="pointer-events-none absolute -left-16 -top-20 hidden h-52 w-52 text-brand-50 sm:block" viewBox="0 0 200 200" aria-hidden>
          <circle cx="100" cy="100" r="100" fill="currentColor" opacity="0.7" />
        </svg>
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <span className="hidden sm:block"><Avatar student={student} size="lg" /></span>
            <span className="sm:hidden"><Avatar student={student} /></span>
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-extrabold tracking-tight text-ink sm:text-[28px]">{t('dash.greeting', { name: student.first_name })}</h1>
              <p className="mt-0.5 text-sm text-ink-secondary">{t('dash.greetingSub')}</p>
              <p className="mt-2 flex flex-wrap gap-1.5 text-xs font-semibold">
                {student.group ? <span className="rounded-full bg-brand-50 px-2.5 py-1 text-brand-700">{student.group.name}</span> : null}
                {student.course ? <span className="rounded-full bg-surface-muted px-2.5 py-1 text-ink-secondary">{student.course.name}</span> : null}
                {student.branch ? <span className="rounded-full bg-surface-muted px-2.5 py-1 text-ink-secondary">{student.branch.name}</span> : null}
              </p>
            </div>
          </div>
          <dl className="grid grid-cols-3 gap-2 sm:gap-3 lg:w-[26rem]">
            {[
              { icon: UserCheck, label: t('dash.attendance'), value: pct(data.attendance.month.percent) },
              { icon: Star, label: t('dash.avgScore'), value: data.performance.average_score ?? '—' },
              { icon: Zap, label: 'XP', value: xp.total },
            ].map(({ icon: Icon, label, value }) => (
              <div key={label} className="rounded-2xl bg-surface-muted/80 px-3 py-3 ring-1 ring-border/60">
                <dt className="flex items-start gap-1.5 text-[11px] font-semibold leading-tight text-ink-secondary"><Icon className="mt-px hidden size-3.5 shrink-0 text-brand-600 sm:block" aria-hidden /><span className="line-clamp-2 break-words">{label}</span></dt>
                <dd className="mt-1 text-xl font-extrabold tabular-nums tracking-tight text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        <NextLessonCard lesson={nextLesson} />

        {/* Current course */}
        <PCard title={t('dash.course')} icon={<GraduationCap className="size-4" aria-hidden />}>
          {progress ? (
            <>
              <p className="truncate text-lg font-extrabold tracking-tight text-ink">{progress.course?.name ?? '—'}</p>
              <p className="text-sm text-ink-secondary">{progress.group?.name}</p>
              <div className="mt-4 flex items-end justify-between">
                <span className="text-3xl font-extrabold tabular-nums tracking-tight text-brand-700">{progress.percent === null ? '—' : `${progress.percent}%`}</span>
                <span className="text-xs font-medium text-ink-muted">{t('dash.lessonsOf', { done: progress.lessons_done, total: progress.lessons_total })}</span>
              </div>
              <Bar value={progress.percent} className="mt-2" />
            </>
          ) : <Empty>{t('hw.noGroup')}</Empty>}
        </PCard>

        {/* XP */}
        <PCard title={t('dash.xp')} icon={<Zap className="size-4" aria-hidden />}
          action={<Link to="/student/achievements" className={CARD_LINK}>{t('dash.details')}</Link>}
          className="md:col-span-2 xl:col-span-1">
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-3xl font-extrabold tabular-nums tracking-tight text-ink">{xp.total}<span className="ml-1 text-base font-bold text-ink-muted">XP</span></p>
              <p className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-bold text-brand-700">
                <Sparkles className="size-3.5" aria-hidden />{t('dash.level', { n: xp.level.level })}
              </p>
            </div>
            <p className="text-right text-xs font-semibold text-brand-600">{t('dash.xpMonth', { n: xp.month.total })}</p>
          </div>
          <Bar value={xp.level.progress} className="mt-4" />
          <p className="mt-1.5 text-xs text-ink-muted">{t('dash.xpToNext', { n: xp.level.next - xp.total })}</p>
        </PCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        {/* Homework preview */}
        <PCard title={t('dash.homeworkNext')} icon={<BookOpenCheck className="size-4" aria-hidden />} className="xl:col-span-2"
          action={<Link to="/student/homework" className={cn(CARD_LINK, 'inline-flex items-center gap-1')}>{t('nav.homework')}<ArrowRight className="size-3.5" aria-hidden /></Link>}>
          {data.homework.not_submitted_count ? (
            <p className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-danger-soft px-3 py-1 text-xs font-semibold text-danger">
              <AlertCircle className="size-3.5" aria-hidden />{t('dash.notSubmittedCount', { n: data.homework.not_submitted_count })}
            </p>
          ) : null}
          {data.homework.open.length ? (
            <div className={cn('grid gap-2.5', data.homework.open.length > 1 && 'md:grid-cols-2')}>{data.homework.open.map((hw) => <HomeworkMini key={hw.id} hw={hw} />)}</div>
          ) : <Empty>{t('hw.emptyNext')}</Empty>}
        </PCard>

        {/* Attendance */}
        <PCard title={t('dash.attendance')} icon={<UserCheck className="size-4" aria-hidden />}
          action={<Link to="/student/attendance" className={CARD_LINK}>{t('dash.details')}</Link>}>
          <div className="flex items-center gap-5">
            <ProgressRing value={data.attendance.month.percent} size={104} label={t('dash.attendance')} />
            <dl className="space-y-2 text-sm">
              <div><dt className="text-xs text-ink-muted">{t('dash.thisMonth')}</dt><dd className="font-bold text-ink">{data.attendance.month.attended} / {data.attendance.month.marked}</dd></div>
              <div><dt className="text-xs text-ink-muted">{t('dash.overall')}</dt><dd className="font-bold text-ink">{pct(data.attendance.overall.percent)}</dd></div>
            </dl>
          </div>
        </PCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <PCard title={t('dash.upcoming')} icon={<CalendarDays className="size-4" aria-hidden />} className="xl:col-span-2">
          {data.upcoming_lessons.length ? (
            <div className="space-y-2.5">{data.upcoming_lessons.map((l) => <LessonRow key={l.id} lesson={l} showDate />)}</div>
          ) : <Empty>{t('dash.noUpcoming')}</Empty>}
        </PCard>
        <PCard title={t('dash.notifications')} icon={<Bell className="size-4" aria-hidden />}>
          <NotificationList items={data.notifications} />
        </PCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <PCard title={t('dash.feedback')} icon={<MessageSquareQuote className="size-4" aria-hidden />} className="xl:col-span-2">
          <FeedbackList items={data.feedback} />
        </PCard>
        <div className="space-y-5">
          <PCard title={t('dash.achievements')} icon={<Trophy className="size-4" aria-hidden />}
            action={<Link to="/student/achievements" className={CARD_LINK}>{t('dash.details')}</Link>}>
            {data.achievements.length ? (
              <ul className="flex flex-wrap gap-2">
                {data.achievements.slice(0, 6).map((a, i) => {
                  const Icon = ACH_ICON[a.code]
                  return (
                    <li key={i} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 ring-1 ring-brand-100">
                      <Icon className="size-3.5" aria-hidden />{achievementText(t, month, a)}
                    </li>
                  )
                })}
              </ul>
            ) : <Empty>{t('dash.noAchievements')}</Empty>}
          </PCard>
          {me.can_view_payments ? (
            <PCard title={t('dash.payments')} icon={<CreditCard className="size-4" aria-hidden />}
              action={<Link to="/student/payments" className={CARD_LINK}>{t('dash.details')}</Link>}>
              {data.payments ? (
                data.payments.has_debt ? (
                  <div>
                    <p className="text-xs font-medium text-ink-secondary">{t('dash.debt')}</p>
                    <p className="text-2xl font-extrabold tabular-nums text-warning">{data.payments.due_now !== '0.00' ? data.payments.due_now : data.payments.debt} {t('common.som')}</p>
                    <p className="mt-1 text-xs text-ink-muted">{t('dash.paid')}: {data.payments.paid} {t('common.som')}</p>
                  </div>
                ) : (
                  <p className="flex items-center gap-2 text-sm font-semibold text-brand-700"><CheckCircle2 className="size-5" aria-hidden />{t('dash.allPaid')}</p>
                )
              ) : <Empty>{t('pay.noContracts')}</Empty>}
            </PCard>
          ) : null}
        </div>
      </div>
    </div>
  )
}
