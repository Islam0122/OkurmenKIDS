import { useState } from 'react'
import { FileSpreadsheet, FileText } from 'lucide-react'

import { reportsApi } from '@/api/reports'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { KPI_STATUS_BADGE_TONE } from '@/features/kpi/kpiStatus'
import { extractErrorMessage } from '@/lib/apiError'
import type { KpiLevel, ReportFiltersInfo, ReportPage, ReportParams, ReportPeriodKey } from '@/types/reports'
import { formatDateShort, formatRuPercent } from '@/utils/format'

/** Presentation helpers shared by the Team Lead / Admin analytics pages
 * (Тренеры, Аналитика, Отчёты). Every figure and KPI level comes from the
 * backend Reports API (services.reports / services.kpi_engine) — nothing
 * here re-computes a KPI. */

export const PERIOD_OPTIONS: { value: ReportPeriodKey; label: string }[] = [
  { value: 'this_week', label: 'Эта неделя' },
  { value: 'this_month', label: 'Этот месяц' },
  { value: 'last_month', label: 'Прошлый месяц' },
  { value: 'this_quarter', label: 'Этот квартал' },
]

export const KPI_LEVEL_LABEL: Record<KpiLevel, string> = {
  good: 'Хороший',
  attention: 'Требует внимания',
  low: 'Низкий',
  no_data: 'Нет данных',
}

export function pct(value: number | null | undefined): string {
  return formatRuPercent(value ?? null)
}

export function KpiBadge({ value, level }: { value: number | null; level: KpiLevel }) {
  return <Badge tone={KPI_STATUS_BADGE_TONE[level]}>{value === null ? KPI_LEVEL_LABEL[level] : pct(value)}</Badge>
}

export function PeriodSelect({ value, onChange }: { value: ReportPeriodKey; onChange: (value: ReportPeriodKey) => void }) {
  return (
    <Select
      aria-label="Период"
      value={value}
      onChange={(event) => onChange(event.target.value as ReportPeriodKey)}
      options={PERIOD_OPTIONS}
    />
  )
}

export function periodCaption(filters: ReportFiltersInfo | undefined): string {
  if (!filters) return ''
  return `${filters.period_label}: ${formatDateShort(filters.start_date)} – ${formatDateShort(filters.end_date)}`
}

export function ReportPagination<T>({ page, onPageChange }: { page: ReportPage<T> | undefined; onPageChange: (page: number) => void }) {
  if (!page) return null
  return <Pagination page={page.page} pageSize={page.page_size} totalCount={page.count} onPageChange={onPageChange} />
}

/** PDF / Excel of the full academy report (teachers, groups, subjects,
 * students, KPI) for the given filters — backend-rendered. */
export function ReportExportButtons({ params }: { params: ReportParams }) {
  const { showToast } = useToast()
  const [pending, setPending] = useState<'pdf' | 'excel' | null>(null)

  async function run(kind: 'pdf' | 'excel') {
    setPending(kind)
    try {
      await (kind === 'pdf' ? reportsApi.downloadPdf(params) : reportsApi.downloadExcel(params))
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сформировать отчёт'), 'error')
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<FileText className="size-4" aria-hidden />}
        isLoading={pending === 'pdf'}
        disabled={pending !== null}
        onClick={() => void run('pdf')}
      >
        PDF
      </Button>
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<FileSpreadsheet className="size-4" aria-hidden />}
        isLoading={pending === 'excel'}
        disabled={pending !== null}
        onClick={() => void run('excel')}
      >
        Excel
      </Button>
    </div>
  )
}
