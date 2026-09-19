import { useState } from 'react'
import type { ComponentType } from 'react'
import {
  Award,
  BarChart3,
  BookOpen,
  CalendarCheck,
  CalendarX2,
  ClipboardCheck,
  Download,
  FolderOpen,
  Gauge,
  MessageSquareText,
  TrendingUp,
  Users,
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
import { useMonthlyReportDetail } from '@/hooks/useMonthlyReports'
import { monthlyReportsApi } from '@/api/monthlyReports'
import { extractErrorMessage } from '@/lib/apiError'
import { formatMonthYear } from '@/utils/format'

import { ReportComment } from './ReportComment'
import { ReportGroupsTable } from './ReportGroupsTable'
import { ReportHeader } from './ReportHeader'
import { ReportKPIBreakdown } from './ReportKPIBreakdown'
import { ReportWeeklyBars } from './ReportWeeklyBars'

export function ReportDetailPage() {
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id)
  const { user } = useAuth()
  const { showToast } = useToast()
  const [isDownloading, setIsDownloading] = useState(false)

  const { data: report, isPending, isError, refetch } = useMonthlyReportDetail(reportId)

  if (isPending) return <LoadingState label="Загружаем отчёт…" />
  if (isError || !report) {
    return <ErrorState title="Не удалось загрузить отчёт" onRetry={() => void refetch()} />
  }

  const { stats } = report
  const canEditComment = user?.role === 'teacher'
  const monthLabel = formatMonthYear(report.year, report.month)

  async function handleDownloadPdf() {
    setIsDownloading(true)
    try {
      await monthlyReportsApi.downloadPdf(reportId, `report-${report!.year}-${String(report!.month).padStart(2, '0')}.pdf`)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось скачать PDF'), 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div>
      <BackLink to="/app/reports">Назад к отчётам</BackLink>

      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink sm:text-2xl">Отчёт преподавателя</h1>
          <p className="mt-1 text-sm text-ink-secondary">{monthLabel}</p>
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
        <ReportHeader report={report} />

        {!stats.has_data ? (
          <EmptyState icon={CalendarX2} title="Нет данных за этот месяц" description={`У вас не было занятий в ${monthLabel.toLowerCase()}.`} />
        ) : (
          <>
            <section>
              <SectionHeader icon={BarChart3} title="Основная статистика" />
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatCard icon={BookOpen} label="Занятия" value={stats.lessons_completed} />
                <StatCard icon={Users2} label="Студенты" value={stats.students_count} />
                <StatCard icon={FolderOpen} label="Группы" value={stats.groups_count} />
                <StatCard icon={CalendarCheck} label="Посещаемость" value={`${stats.attendance.rate}%`} />
                <StatCard icon={ClipboardCheck} label="Домашние задания" value={`${stats.homework.submission_rate}%`} />
                <StatCard
                  icon={Award}
                  label="Итоговый KPI"
                  value={`${stats.kpi.total}%`}
                  tone={stats.kpi.total >= 85 ? 'default' : stats.kpi.total >= 60 ? 'warning' : 'danger'}
                />
              </div>
            </section>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={Users} title="Работа преподавателя" />
                <div className="mt-1 divide-y divide-border">
                  <WorkRow label="Проведено занятий" value={stats.lessons_completed} />
                  <WorkRow label="Выдано домашних заданий" value={stats.homework.assigned} />
                  <WorkRow label="Проверено домашних заданий" value={stats.homework.checked} />
                  <WorkRow label="Работа со студентами" value={stats.students_count} />
                </div>
              </section>

              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={Gauge} title="Показатели KPI" />
                <ReportKPIBreakdown kpi={stats.kpi} />
              </section>
            </div>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={FolderOpen} title="Группы" />
                <ReportGroupsTable groups={stats.groups} />
              </section>

              <section className="rounded-xl border border-border bg-surface p-5">
                <SectionHeader icon={TrendingUp} title="Динамика посещаемости" subtitle="Посещаемость по неделям" />
                <ReportWeeklyBars weeks={stats.weekly_dynamics} />
              </section>
            </div>
          </>
        )}

        <section className="rounded-xl border border-border bg-surface p-5">
          <SectionHeader icon={MessageSquareText} title="Итог месяца" />
          <ReportComment report={report} canEdit={canEditComment} />
        </section>

        <section className="rounded-xl border border-border bg-surface p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Signature label="Преподаватель" value={`${report.teacher.user.last_name} ${report.teacher.user.first_name}`.trim()} />
            <Signature label="Администратор" value="______________________" />
            <Signature label="Дата" value={new Date(report.updated_at).toLocaleDateString('ru-RU')} />
          </div>
        </section>
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

function WorkRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-2.5 text-sm">
      <span className="text-ink-secondary">{label}</span>
      <span className="font-semibold text-ink">{value}</span>
    </div>
  )
}

function Signature({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="mt-1 font-medium text-ink">{value}</p>
    </div>
  )
}
