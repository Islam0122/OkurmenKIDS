import { useState } from 'react'
import { FileText, Plus } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { useMonthlyReportsList } from '@/hooks/useMonthlyReports'

import { CreateReportModal } from './CreateReportModal'
import { ReportCard } from './ReportCard'
import { ReportCardSkeleton } from './ReportCardSkeleton'

export function ReportsListPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const { data, isPending, isError, refetch } = useMonthlyReportsList()

  return (
    <div>
      <PageHeader
        title="Мои отчёты"
        description="Ежемесячные отчёты о вашей работе"
        actions={
          <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setIsCreateOpen(true)}>
            Создать отчёт
          </Button>
        }
      />

      {isPending ? (
        <div className="space-y-3">
          <ReportCardSkeleton />
          <ReportCardSkeleton />
          <ReportCardSkeleton />
        </div>
      ) : null}

      {isError ? <ErrorState title="Не удалось загрузить отчёты" onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Отчётов пока нет"
          description="Создайте первый ежемесячный отчёт о своей работе."
          action={<Button onClick={() => setIsCreateOpen(true)}>Создать первый отчёт</Button>}
        />
      ) : null}

      {data && data.results.length > 0 ? (
        <div className="space-y-3">
          {data.results.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </div>
      ) : null}

      <CreateReportModal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
    </div>
  )
}
