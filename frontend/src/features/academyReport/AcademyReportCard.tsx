import { useState } from 'react'
import { ArrowRight, Download, School } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { academyReportsApi } from '@/api/academyReports'
import { extractErrorMessage } from '@/lib/apiError'
import type { AcademyMonthlyReport } from '@/types/academyReport'
import { formatMonthYear, formatRuPercent } from '@/utils/format'

export function AcademyReportCard({ report }: { report: AcademyMonthlyReport }) {
  const { stats } = report
  const { showToast } = useToast()
  const [isDownloading, setIsDownloading] = useState(false)

  async function handleDownloadPdf() {
    setIsDownloading(true)
    try {
      await academyReportsApi.downloadPdf(report.id, `academy-report-${report.year}-${String(report.month).padStart(2, '0')}.pdf`)
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось скачать PDF'), 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-5 transition-colors hover:border-brand-200 hover:bg-brand-50/30">
      <Link to={`/app/academy-report/${report.id}`} className="block">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
            <School className="size-4" aria-hidden />
          </span>
          <h3 className="font-semibold text-ink">{formatMonthYear(report.year, report.month)}</h3>
        </div>

        {stats.has_data ? (
          <p className="mt-4 text-sm text-ink-secondary">
            {stats.students_count} студентов · {stats.groups_count} групп · {stats.teachers_count} тренеров
          </p>
        ) : (
          <p className="mt-4 text-sm text-ink-muted">Нет данных за этот месяц</p>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
          {stats.has_data ? (
            <p className="text-sm">
              <span className="text-ink-secondary">Посещаемость </span>
              <span className="font-semibold text-ink">{formatRuPercent(stats.attendance.rate)}</span>
            </p>
          ) : (
            <span />
          )}
          <span className="inline-flex items-center gap-1 text-sm font-medium text-brand-600">
            Открыть <ArrowRight className="size-3.5" aria-hidden />
          </span>
        </div>
      </Link>

      <Button
        variant="secondary"
        size="sm"
        className="mt-3 w-full"
        leftIcon={<Download className="size-3.5" aria-hidden />}
        onClick={() => void handleDownloadPdf()}
        isLoading={isDownloading}
      >
        Скачать PDF
      </Button>
    </div>
  )
}
