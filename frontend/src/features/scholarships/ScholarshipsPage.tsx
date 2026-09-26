import { useState } from 'react'
import { Award, CheckCircle2, ClipboardList, RefreshCw, Users } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import {
  useApproveScholarship,
  useRecalculateScholarship,
  useRequiredFeedback,
  useScholarshipAnalytics,
  useScholarshipPeriods,
  useScholarshipRanking,
} from '@/hooks/useScholarships'
import { extractErrorMessage } from '@/lib/apiError'
import {
  ELIGIBILITY_LABELS,
  type EligibilityStatus,
  type RequiredFeedbackItem,
  type ScholarshipPeriod,
} from '@/types/scholarship'
import { formatDate } from '@/utils/format'

import { FeedbackModal } from './FeedbackModal'

const ELIGIBILITY_TONES: Record<EligibilityStatus, BadgeTone> = {
  eligible: 'success',
  not_full_period: 'info',
  inactive: 'danger',
  no_data: 'muted',
  incomplete_data: 'warning',
  below_threshold: 'muted',
}

function periodLabel(period: ScholarshipPeriod): string {
  return `${period.title || 'Стипендия'} · ${formatDate(period.period_start)} — ${formatDate(period.period_end)}`
}

function PeriodPicker({
  periods,
  value,
  onChange,
}: {
  periods: ScholarshipPeriod[]
  value: number
  onChange: (id: number) => void
}) {
  return (
    <div className="mb-5 max-w-md">
      <label htmlFor="scholarship-period" className="mb-1.5 block text-sm font-medium text-ink">
        Период оценки
      </label>
      <Select
        id="scholarship-period"
        value={String(value)}
        onChange={(event) => onChange(Number(event.target.value))}
        options={periods.map((p) => ({
          value: String(p.id),
          label: `${periodLabel(p)}${p.status === 'approved' ? ' · утверждён' : ''}`,
        }))}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Trainer: feedback to-do list
// ---------------------------------------------------------------------------

function TrainerFeedbackList({ period }: { period: ScholarshipPeriod }) {
  const { data, isPending, isError, refetch } = useRequiredFeedback(period.id)
  const [selected, setSelected] = useState<RequiredFeedbackItem | null>(null)
  const readOnly = period.status !== 'draft'

  if (isPending) return <LoadingState label="Загружаем список студентов…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />
  if (data.items.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title="Нет студентов для оценки"
        description="В этом периоде у вас не было занятий с отметкой посещаемости."
      />
    )
  }

  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <StatCard label="Студентов и предметов" value={data.total} icon={Users} />
        <StatCard
          label="Ожидают оценки"
          value={data.missing}
          icon={ClipboardList}
          tone={data.missing > 0 ? 'warning' : 'default'}
        />
      </div>
      {readOnly ? (
        <p className="mb-3 text-sm text-ink-muted">Период утверждён — оценки доступны только для просмотра.</p>
      ) : null}
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {data.items.map((item) => (
          <li key={`${item.student}-${item.subject}`} className="flex items-center justify-between gap-3 p-4">
            <div className="min-w-0">
              <p className="truncate font-medium text-ink">{item.student_name}</p>
              <p className="text-sm text-ink-secondary">{item.subject_name}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              {item.feedback ? (
                <Badge tone="success">{item.feedback.score}</Badge>
              ) : (
                <Badge tone="warning">Нет оценки</Badge>
              )}
              <Button size="sm" variant={item.feedback ? 'secondary' : 'primary'} onClick={() => setSelected(item)}>
                {readOnly ? 'Открыть' : item.feedback ? 'Изменить' : 'Оценить'}
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <FeedbackModal periodId={period.id} item={selected} readOnly={readOnly} onClose={() => setSelected(null)} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Admin: ranking overview
// ---------------------------------------------------------------------------

function AdminRanking({ period }: { period: ScholarshipPeriod }) {
  const [page, setPage] = useState(1)
  const [confirmApprove, setConfirmApprove] = useState(false)
  const ranking = useScholarshipRanking(period.id, page)
  const analytics = useScholarshipAnalytics(period.id)
  const recalculate = useRecalculateScholarship()
  const approve = useApproveScholarship()
  const { showToast } = useToast()
  const isDraft = period.status === 'draft'

  async function run(action: 'recalculate' | 'approve') {
    try {
      if (action === 'recalculate') await recalculate.mutateAsync(period.id)
      else await approve.mutateAsync(period.id)
      showToast(action === 'recalculate' ? 'Баллы пересчитаны' : 'Стипендии утверждены', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setConfirmApprove(false)
    }
  }

  return (
    <>
      {analytics.data ? (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Оценено студентов" value={analytics.data.total_evaluated} icon={Users} />
          <StatCard label="Допущено" value={analytics.data.total_eligible} icon={CheckCircle2} />
          <StatCard
            label="Стипендиатов"
            value={`${analytics.data.total_recipients} / ${analytics.data.max_recipients ?? '∞'}`}
            icon={Award}
            hint={analytics.data.max_recipients === null ? 'Без ограничения' : undefined}
          />
          <StatCard
            label="Неполные данные"
            value={analytics.data.incomplete_data}
            icon={ClipboardList}
            tone={analytics.data.incomplete_data > 0 ? 'warning' : 'default'}
            hint="Не хватает оценок тренеров"
          />
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2">
        {isDraft ? (
          <>
            <Button
              variant="secondary"
              leftIcon={<RefreshCw className="size-4" aria-hidden />}
              isLoading={recalculate.isPending}
              onClick={() => void run('recalculate')}
            >
              Пересчитать
            </Button>
            <Button leftIcon={<CheckCircle2 className="size-4" aria-hidden />} onClick={() => setConfirmApprove(true)}>
              Утвердить стипендии
            </Button>
          </>
        ) : (
          <Badge tone="success">Утверждено {period.approved_at ? formatDate(period.approved_at) : ''}</Badge>
        )}
      </div>

      {ranking.isPending ? <LoadingState label="Загружаем рейтинг…" /> : null}
      {ranking.isError ? <ErrorState onRetry={() => void ranking.refetch()} /> : null}
      {ranking.data ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-surface-hover text-left text-xs uppercase text-ink-muted">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Студент</th>
                <th className="px-3 py-2">Итог</th>
                <th className="px-3 py-2">Посещ.</th>
                <th className="px-3 py-2">ДЗ</th>
                <th className="px-3 py-2">Тренер</th>
                <th className="px-3 py-2">Допуск</th>
                <th className="px-3 py-2">Стипендия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {ranking.data.results.map((row) => (
                <tr key={row.id} className={row.award_status ? 'bg-brand-50/40' : undefined}>
                  <td className="px-3 py-2 font-semibold">{row.rank ?? '—'}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium text-ink">{row.student_name}</p>
                    <p className="text-xs text-ink-muted">{row.group_name || '—'}</p>
                  </td>
                  <td className="px-3 py-2 font-semibold">{row.overall_score ?? '—'}</td>
                  <td className="px-3 py-2">{row.attendance_score ?? '—'}</td>
                  <td className="px-3 py-2">{row.homework_score ?? '—'}</td>
                  <td className="px-3 py-2">{row.feedback_score ?? '—'}</td>
                  <td className="px-3 py-2" title={row.ineligibility_reason}>
                    <Badge tone={ELIGIBILITY_TONES[row.eligibility_status]}>
                      {ELIGIBILITY_LABELS[row.eligibility_status]}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    {row.award_status === 'approved' ? 'Утверждена' : row.award_status === 'pending' ? 'Ожидает' : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {ranking.data && ranking.data.count > ranking.data.results.length ? (
        <Pagination page={page} pageSize={20} totalCount={ranking.data.count} onPageChange={setPage} />
      ) : null}
      <p className="mt-3 text-sm text-ink-muted">
        Разбивка по предметам, история студента и оценки тренеров — в админ-панели, раздел «Стипендии».
      </p>

      <ConfirmDialog
        isOpen={confirmApprove}
        title="Утвердить стипендии?"
        message="После утверждения пересчёт периода невозможен, а тренеры больше не смогут менять оценки."
        confirmLabel="Утвердить"
        isLoading={approve.isPending}
        onConfirm={() => void run('approve')}
        onCancel={() => setConfirmApprove(false)}
      />
    </>
  )
}

// ---------------------------------------------------------------------------

export function ScholarshipsPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { data, isPending, isError, refetch } = useScholarshipPeriods()
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const periods = data?.results ?? []
  const period = periods.find((p) => p.id === selectedId) ?? periods[0]

  return (
    <div>
      <PageHeader
        title="Стипендии"
        description={
          isAdmin
            ? 'Ежемесячный рейтинг студентов по всем предметам'
            : 'Оценки ваших студентов для стипендиального рейтинга'
        }
      />
      {isPending ? <LoadingState /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && !period ? (
        <EmptyState
          icon={Award}
          title="Периодов пока нет"
          description="Периоды создаёт администратор в разделе «Стипендии» или они формируются автоматически после окончания месяца."
        />
      ) : null}
      {period ? (
        <>
          <PeriodPicker periods={periods} value={period.id} onChange={setSelectedId} />
          {isAdmin ? <AdminRanking key={period.id} period={period} /> : <TrainerFeedbackList period={period} />}
        </>
      ) : null}
    </div>
  )
}
