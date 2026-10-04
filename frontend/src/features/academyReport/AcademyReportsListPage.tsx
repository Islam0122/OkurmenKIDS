import { useState } from 'react'
import { School } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { PeriodSelect, ReportExportButtons } from '@/features/analytics/reportUi'
import { useAcademyReportsList, useCreateAcademyReport } from '@/hooks/useAcademyReports'
import { useAuth } from '@/hooks/useAuth'
import type { ReportPeriodKey } from '@/types/reports'
import { extractErrorMessage } from '@/lib/apiError'
import { getYearOptions, MONTH_OPTIONS } from '@/features/reports/months'

import { AcademyReportCard } from './AcademyReportCard'
import { AcademyReportCardSkeleton } from './AcademyReportCardSkeleton'

const YEAR_OPTIONS = getYearOptions()

/** Отчёт по тренерам, группам, студентам и предметам + KPI, посещаемость и
 * ДЗ за период — PDF/Excel from the Reports API (Admin and Team Lead). */
function ReportsExportCard() {
  const [period, setPeriod] = useState<ReportPeriodKey>('this_month')
  return (
    <div className="mb-6 card card-body flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <p className="font-medium text-ink">Сводный отчёт за период</p>
        <p className="text-sm text-ink-secondary">Тренеры, группы, студенты, предметы, KPI, посещаемость и ДЗ</p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-48">
          <PeriodSelect value={period} onChange={setPeriod} />
        </div>
        <ReportExportButtons params={{ period }} />
      </div>
    </div>
  )
}

export function AcademyReportsListPage() {
  const today = new Date()
  const [year, setYear] = useState(String(today.getFullYear()))
  const [month, setMonth] = useState(String(today.getMonth() + 1))

  const navigate = useNavigate()
  const { showToast } = useToast()
  const { data, isPending, isError, refetch } = useAcademyReportsList()
  const mutation = useCreateAcademyReport()
  const { user } = useAuth()
  // Creating a month's report is an Admin write; a Team Lead reads existing ones.
  const canCreate = user?.role === 'admin'

  async function handleOpenReport() {
    try {
      const result = await mutation.mutateAsync({ year: Number(year), month: Number(month) })
      navigate(`/app/academy-report/${result.report.id}`)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось открыть отчёт'), 'error')
    }
  }

  return (
    <div>
      <PageHeader title="Отчёты академии" description="Ежемесячная статистика и результаты академии" />

      {canCreate ? (
      <div className="mb-6 flex flex-wrap items-end gap-2 card card-body">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-ink-secondary">Год</label>
          <Select value={year} onChange={(event) => setYear(event.target.value)} options={YEAR_OPTIONS} className="w-28" />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-ink-secondary">Месяц</label>
          <Select value={month} onChange={(event) => setMonth(event.target.value)} options={MONTH_OPTIONS} className="w-40" />
        </div>
        <Button onClick={() => void handleOpenReport()} isLoading={mutation.isPending}>
          Открыть отчёт
        </Button>
      </div>
      ) : null}

      {/* Full academy report (trainers, groups, students, subjects, KPI) for a period. */}
      <ReportsExportCard />

      {isPending ? (
        <div className="space-y-3">
          <AcademyReportCardSkeleton />
          <AcademyReportCardSkeleton />
          <AcademyReportCardSkeleton />
        </div>
      ) : null}

      {isError ? <ErrorState title="Не удалось загрузить отчёты" onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState
          icon={School}
          title="Отчётов пока нет"
          description={
            canCreate
              ? 'Выберите год и месяц выше, чтобы открыть первый отчёт академии.'
              : 'Ежемесячные отчёты появятся, когда их сформирует администратор. Сводный отчёт за период доступен выше.'
          }
        />
      ) : null}

      {data && data.results.length > 0 ? (
        <div className="space-y-3">
          {data.results.map((report) => (
            <AcademyReportCard key={report.id} report={report} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
