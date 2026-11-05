import { useState } from 'react'
import { FileBarChart, History, Plus } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { useAuth } from '@/hooks/useAuth'
import { useParentReport, useParentReportHistory } from '@/hooks/useParentReports'
import type { ParentReportListItem, ParentReportStatus } from '@/types/parentReports'
import { formatDateShort } from '@/utils/format'

import { ReportGeneratorModal } from './ReportGeneratorModal'
import { ReportResult } from './ReportResult'

const STATUS_TONE: Record<ParentReportStatus, BadgeTone> = { ready: 'success', partial: 'warning', failed: 'danger' }
const PAGE_SIZE = 20

/** Admin and Trainer generate; a Team Lead reads the history only (the backend enforces it). */
export function canGenerateReports(role: string | undefined): boolean {
  return role === 'admin' || role === 'teacher'
}

function formatCreated(value: string): string {
  const date = new Date(value)
  return `${date.toLocaleDateString('ru-RU')} ${date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`
}

/** Group → KPI → «Отчёты»: «Создать отчёт» + the report history of the group. */
export function ParentReportsSection({ groupId }: { groupId: number }) {
  const { user } = useAuth()
  const canGenerate = canGenerateReports(user?.role)
  const [isGeneratorOpen, setGeneratorOpen] = useState(false)
  const [openedId, setOpenedId] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch } = useParentReportHistory({ group: groupId, page })

  return (
    <section aria-label="Отчёты для родителей" className="space-y-4">
      <div className="card card-body flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="section-title flex items-center gap-2">
            <FileBarChart className="size-5 text-brand-500" aria-hidden /> Отчёты для родителей
          </h3>
          <p className="mt-1 text-sm text-ink-secondary">
            Посещаемость, домашние задания, оценки и тесты за период — картинка OkurmenKIDS и текст для WhatsApp.
            Всё считается по данным LMS.
          </p>
        </div>
        {canGenerate ? (
          <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setGeneratorOpen(true)}>
            Создать отчёт
          </Button>
        ) : null}
      </div>

      <h3 className="section-title flex items-center gap-2">
        <History className="size-5 text-ink-secondary" aria-hidden /> История отчётов
      </h3>
      {isPending ? (
        <LoadingState label="Загружаем историю…" />
      ) : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : data.results.length === 0 ? (
        <EmptyState
          icon={FileBarChart}
          title="Отчётов пока нет"
          description={canGenerate ? 'Нажмите «Создать отчёт», чтобы сформировать первый.' : undefined}
        />
      ) : (
        <>
          <DataTable<ParentReportListItem>
            rows={data.results}
            getRowKey={(row) => row.id}
            onRowClick={(row) => setOpenedId(row.id)}
            columns={[
              { key: 'created', header: 'Создан', render: (row) => formatCreated(row.created_at) },
              {
                key: 'period',
                header: 'Период',
                render: (row) => `${formatDateShort(row.start_date)} — ${formatDateShort(row.end_date)}`,
              },
              { key: 'type', header: 'Тип', render: (row) => row.report_type_display },
              { key: 'language', header: 'Язык', render: (row) => row.language_display },
              { key: 'format', header: 'Формат', render: (row) => row.output_format_display },
              {
                key: 'status',
                header: 'Статус',
                render: (row) => <Badge tone={STATUS_TONE[row.status]}>{row.status_display}</Badge>,
              },
              { key: 'author', header: 'Автор', render: (row) => row.created_by_name || '—' },
            ]}
          />
          {data.count > PAGE_SIZE ? (
            <Pagination page={page} pageSize={PAGE_SIZE} totalCount={data.count} onPageChange={setPage} />
          ) : null}
        </>
      )}

      <ReportGeneratorModal isOpen={isGeneratorOpen} onClose={() => setGeneratorOpen(false)} groupId={groupId} />
      <ReportDetailModal reportId={openedId} canEdit={canGenerate} onClose={() => setOpenedId(null)} onOpen={setOpenedId} />
    </section>
  )
}

function ReportDetailModal({
  reportId,
  canEdit,
  onClose,
  onOpen,
}: {
  reportId: number | null
  canEdit: boolean
  onClose: () => void
  onOpen: (id: number) => void
}) {
  return (
    <Modal isOpen={reportId !== null} onClose={onClose} title="Отчёт для родителей" size="xl">
      {reportId !== null ? <ReportDetailBody reportId={reportId} canEdit={canEdit} onOpen={onOpen} /> : null}
    </Modal>
  )
}

function ReportDetailBody({ reportId, canEdit, onOpen }: { reportId: number; canEdit: boolean; onOpen: (id: number) => void }) {
  const { data, isPending, isError, refetch } = useParentReport(reportId)
  if (isPending) return <LoadingState label="Загружаем отчёт…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />
  return <ReportResult key={data.id} report={data} canEdit={canEdit} onRegenerated={(fresh) => onOpen(fresh.id)} />
}
