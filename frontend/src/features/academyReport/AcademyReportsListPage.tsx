import { useState } from 'react'
import { School } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useAcademyReportsList, useCreateAcademyReport } from '@/hooks/useAcademyReports'
import { extractErrorMessage } from '@/lib/apiError'
import { getYearOptions, MONTH_OPTIONS } from '@/features/reports/months'

import { AcademyReportCard } from './AcademyReportCard'
import { AcademyReportCardSkeleton } from './AcademyReportCardSkeleton'

const YEAR_OPTIONS = getYearOptions()

export function AcademyReportsListPage() {
  const today = new Date()
  const [year, setYear] = useState(String(today.getFullYear()))
  const [month, setMonth] = useState(String(today.getMonth() + 1))

  const navigate = useNavigate()
  const { showToast } = useToast()
  const { data, isPending, isError, refetch } = useAcademyReportsList()
  const mutation = useCreateAcademyReport()

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
      <PageHeader title="🏫 Отчёты академии" description="Ежемесячная статистика и результаты академии" />

      <div className="mb-5 flex flex-wrap items-end gap-2 rounded-xl border border-border bg-surface p-4">
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
          description="Выберите год и месяц выше, чтобы открыть первый отчёт академии."
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
