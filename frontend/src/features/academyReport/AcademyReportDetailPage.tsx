import { useState } from 'react'
import type { ComponentType } from 'react'
import {
  AlertTriangle,
  Award,
  BarChart3,
  BookOpen,
  CalendarCheck,
  CalendarX2,
  ClipboardCheck,
  DoorOpen,
  Download,
  FolderOpen,
  Gauge,
  GraduationCap,
  MessageSquareText,
  PieChart,
  TrendingUp,
  Users2,
} from 'lucide-react'
import { useParams } from 'react-router-dom'

import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { useAcademyReportDetail } from '@/hooks/useAcademyReports'
import { academyReportsApi } from '@/api/academyReports'
import { WeeklyAttendanceChart } from '@/features/reports/WeeklyAttendanceChart'
import { extractErrorMessage } from '@/lib/apiError'
import { formatMonthYear, formatRuPercent } from '@/utils/format'

import { AcademyReportComment } from './AcademyReportComment'
import { AcademyReportGroupsTable } from './AcademyReportGroupsTable'
import { AcademyReportKPIBreakdown } from './AcademyReportKPIBreakdown'
import { AcademyReportTeachersTable } from './AcademyReportTeachersTable'

export function AcademyReportDetailPage() {
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id)
  const { user } = useAuth()
  const { showToast } = useToast()
  const [isDownloading, setIsDownloading] = useState(false)

  const { data: report, isPending, isError, refetch } = useAcademyReportDetail(reportId)

  if (isPending) return <LoadingState label="Загружаем отчёт…" />
  if (isError || !report) {
    return <ErrorState title="Не удалось загрузить отчёт" onRetry={() => void refetch()} />
  }

  const { stats } = report
  const canEditComment = user?.role === 'admin'
  const monthLabel = formatMonthYear(report.year, report.month)

  async function handleDownloadPdf() {
    setIsDownloading(true)
    try {
      await academyReportsApi.downloadPdf(reportId, `academy-report-${report!.year}-${String(report!.month).padStart(2, '0')}.pdf`)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось скачать PDF'), 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div>
      <BackLink to="/app/academy-report">Назад к отчётам</BackLink>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink sm:text-2xl">🏫 Отчёт академии</h1>
          <p className="mt-1 text-sm font-medium text-brand-600">{monthLabel}</p>
          <p className="mt-0.5 text-sm text-ink-secondary">Ежемесячный отчёт OKURMENKIDS</p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          leftIcon={<Download className="size-4" aria-hidden />}
          onClick={() => void handleDownloadPdf()}
          isLoading={isDownloading}
        >
          Скачать PDF
        </Button>
      </div>

      <div className="space-y-5">
        {!stats.has_data ? (
          <EmptyState icon={CalendarX2} title="Нет данных за этот месяц" description={`За ${monthLabel.toLowerCase()} пока нет данных для отчёта.`} />
        ) : (
          <>
            <section>
              <SectionHeader icon={BarChart3} title="Основная статистика" />
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatCard icon={Users2} label="Студенты" value={stats.students_count} />
                <StatCard icon={FolderOpen} label="Группы" value={stats.groups_count} />
                <StatCard icon={GraduationCap} label="Преподаватели" value={stats.teachers_count} />
                <StatCard icon={BookOpen} label="Занятия" value={stats.lessons_completed} />
                <StatCard icon={CalendarCheck} label="Посещаемость" value={formatRuPercent(stats.attendance.rate)} />
                <StatCard
                  icon={Award}
                  label="Средний KPI"
                  value={formatRuPercent(stats.kpi.total)}
                  tone={stats.kpi.total >= 85 ? 'default' : stats.kpi.total >= 60 ? 'warning' : 'danger'}
                />
              </div>
            </section>

            <section className="rounded-xl border border-border bg-surface p-5">
              <SectionHeader icon={Users2} title="Студенты" />
              <div className="divide-y divide-border">
                <WorkRow label="Всего активных студентов" value={stats.students.active} />
                <WorkRow label="Новые студенты" value={stats.students.new} />
                <WorkRow label="Завершили обучение" value={stats.students.completed} />
                <WorkRow label="Вышли из курса" value={stats.students.left} />
              </div>
            </section>

            <section className="rounded-xl border border-border bg-surface p-5">
              <SectionHeader icon={FolderOpen} title="Статистика групп" />
              <div className="divide-y divide-border">
                <WorkRow label="Всего групп" value={stats.group_stats.total} />
                <WorkRow label="Активные группы" value={stats.group_stats.active} />
                <WorkRow label="Завершённые группы" value={stats.group_stats.completed} />
                <WorkRow label="Студентов в активных группах" value={stats.group_stats.students_active} />
                <WorkRow label="Студентов в завершённых группах" value={stats.group_stats.students_completed} />
              </div>
            </section>

            <section className="rounded-xl border border-border bg-surface p-5">
              <SectionHeader icon={FolderOpen} title="Группы" />
              <AcademyReportGroupsTable groups={stats.groups} />
            </section>

            <section className="rounded-xl border border-border bg-surface p-5">
              <SectionHeader icon={GraduationCap} title="Преподаватели" />
              <AcademyReportTeachersTable teachers={stats.teachers} />
            </section>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={BookOpen} title="Учебный процесс" />
                <div className="divide-y divide-border">
                  <WorkRow label="Запланировано занятий" value={stats.lessons.scheduled} />
                  <WorkRow label="Проведено занятий" value={stats.lessons.completed} />
                  <WorkRow label="Отменено занятий" value={stats.lessons.cancelled} />
                  <WorkRow label="Перенесено занятий" value={stats.lessons.rescheduled} />
                  <WorkRow label="Средняя посещаемость" value={formatRuPercent(stats.lessons.attendance_rate)} />
                </div>
              </section>

              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={ClipboardCheck} title="Домашние задания" />
                <div className="divide-y divide-border">
                  <WorkRow label="Выдано домашних заданий" value={stats.homework.assigned} />
                  <WorkRow label="Проверено домашних заданий" value={stats.homework.checked} />
                  <WorkRow label="Ожидают проверки" value={stats.homework.pending_review} />
                  <WorkRow
                    label="Процент проверки"
                    value={stats.homework.checked_rate === null ? null : formatRuPercent(stats.homework.checked_rate)}
                  />
                </div>
              </section>
            </div>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={TrendingUp} title="Динамика академии" subtitle="Посещаемость по неделям" />
                <WeeklyAttendanceChart weeks={stats.weekly_dynamics} />
              </section>

              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={Gauge} title="Показатели академии" />
                <AcademyReportKPIBreakdown kpi={stats.kpi} />
              </section>
            </div>

            <section className="rounded-xl border border-border bg-surface p-5">
              <SectionHeader icon={DoorOpen} title="Движение студентов" />
              <div className="divide-y divide-border">
                <WorkRow label="Вышли из курса за месяц" value={stats.movement.left} />
                <WorkRow label="Завершили обучение" value={stats.movement.completed.count} />
                <WorkRow label="Активные группы" value={stats.movement.active_groups} />
                <WorkRow label="Завершённые группы" value={stats.movement.completed_groups} />
              </div>
            </section>

            <section className="rounded-xl border border-border bg-surface p-5">
              <SectionHeader icon={PieChart} title="Разбивка по причинам ухода" />
              {stats.movement.reasons.length === 0 ? (
                <p className="text-sm text-ink-muted">За выбранный период уходов студентов не зарегистрировано.</p>
              ) : (
                <div className="divide-y divide-border">
                  {stats.movement.reasons.map((row) => (
                    <div key={row.reason} className="flex items-center justify-between py-2.5 text-sm">
                      <span className="text-ink-secondary">{row.reason_display}</span>
                      <span className="font-semibold text-ink">
                        {row.count} · {formatRuPercent(row.percent)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {stats.attention.length > 0 ? (
              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={AlertTriangle} title="Требует внимания" />
                <ul className="space-y-2">
                  {stats.attention.map((item, index) => (
                    <li key={index} className="flex gap-2 text-sm text-ink-secondary">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
                      {item.message}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        )}

        <section className="rounded-xl border border-border bg-surface p-5">
          <SectionHeader icon={MessageSquareText} title="Итог месяца" />
          <AcademyReportComment report={report} canEdit={canEditComment} />
        </section>

        <p className="text-center text-xs text-ink-muted">
          Дата формирования отчёта: {new Date(report.updated_at).toLocaleString('ru-RU')}
        </p>
      </div>
    </div>
  )
}

function SectionHeader({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  subtitle?: string
}) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Icon className="size-4 shrink-0 text-brand-600" aria-hidden />
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="text-xs text-ink-secondary">{subtitle}</p> : null}
      </div>
    </div>
  )
}

function WorkRow({
  label,
  value,
  nullLabel = 'Нет данных',
}: {
  label: string
  value: number | string | null | undefined
  /** Shown when `value` is null/undefined/NaN — "Нет данных" (feature
   * exists, nothing to show) and "Функция пока не поддерживается" (no such
   * status yet) must never be confused, so callers pick which one applies. */
  nullLabel?: string
}) {
  const isMissing = value === null || value === undefined || (typeof value === 'number' && Number.isNaN(value))
  return (
    <div className="flex items-center justify-between py-2.5 text-sm">
      <span className="text-ink-secondary">{label}</span>
      <span className="font-semibold text-ink">{isMissing ? nullLabel : value}</span>
    </div>
  )
}
