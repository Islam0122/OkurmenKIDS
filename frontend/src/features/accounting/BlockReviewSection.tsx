import { useState } from 'react'
import { TriangleAlert } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Tabs } from '@/components/ui/Tabs'
import { useAccountingMutation, useBlockEstimates, useCycleAccruals } from '@/hooks/useAccounting'
import type { CycleAccrual } from '@/types/accounting'

import { EstimateStatusBadge } from './EstimateCard'
import { ReasonModal, Section, formatDate, som, useRunner } from './shared'

type Tab = 'review' | 'estimates'

/**
 * Начисления за блоки, требующие решения бухгалтера (смена тренера внутри
 * блока, второй блок группы за месяц), и предварительные оценки открытых
 * блоков. Оценки — не начисления: в итоги и отчёты они не входят.
 */
export function BlockReviewSection({ canOperate }: { canOperate: boolean }) {
  const [tab, setTab] = useState<Tab>('review')
  const review = useCycleAccruals({ status: 'REVIEW_REQUIRED' })
  const count = review.data?.count ?? 0
  return (
    <Section title="Блоки: проверка и предварительный расчёт">
      <Tabs
        aria-label="Блоки"
        items={[
          { key: 'review', label: count ? `Требуют проверки (${count})` : 'Требуют проверки' },
          { key: 'estimates', label: 'Предварительные оценки' },
        ] as const}
        value={tab}
        onChange={setTab}
      />
      <div className="mt-4">
        {tab === 'review' ? <ReviewList query={review} canOperate={canOperate} /> : <EstimatesTable />}
      </div>
    </Section>
  )
}

function ReviewList({ query, canOperate }: { query: ReturnType<typeof useCycleAccruals>; canOperate: boolean }) {
  const [deciding, setDeciding] = useState<{ accrual: CycleAccrual; confirm: boolean } | null>(null)
  const { run } = useRunner()
  const mutate = useAccountingMutation((args: { id: number; confirm: boolean; reason: string }) =>
    accountingApi.reviewCycleAccrual(args.id, args.confirm, args.reason))

  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState onRetry={() => query.refetch()} />
  const rows = query.data?.results ?? []
  if (rows.length === 0) return <EmptyState title="Спорных начислений нет" description="Все завершённые блоки начислены автоматически." />
  return (
    <>
      <div className="space-y-3">
        {rows.map((a) => (
          <div key={a.id} className="card p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-ink">{a.employee_name} · {a.group_name}, блок №{a.cycle_number}</p>
                <p className="text-sm text-ink-secondary">
                  {a.course_name} · завершён {formatDate(a.completed_on)} · {a.student_count} × {som(a.course_price)} × {Number(a.percentage)}% ={' '}
                  <b>{som(a.amount)}</b> · плановая выплата {formatDate(a.planned_payment_date)}
                </p>
              </div>
              <Badge tone="warning"><TriangleAlert className="mr-1 inline size-3" aria-hidden />{a.status_display}</Badge>
            </div>
            <ul className="mt-2 space-y-1 text-sm text-warning">
              {a.review_reasons.length
                ? a.review_reasons.map((r) => <li key={r}>• {r}</li>)
                : <li>• {a.note || 'Причина не сохранена — проверьте уроки блока.'}</li>}
            </ul>
            {canOperate ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" onClick={() => setDeciding({ accrual: a, confirm: true })}>Подтвердить начисление</Button>
                <Button size="sm" variant="secondary" onClick={() => setDeciding({ accrual: a, confirm: false })}>Отменить начисление</Button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <ReasonModal
        isOpen={deciding !== null}
        title={deciding?.confirm ? 'Подтвердить начисление за блок' : 'Отменить начисление за блок'}
        description={deciding?.confirm
          ? 'Начисление войдёт в ближайший расчёт сотрудника. Укажите основание — оно сохранится в журнале.'
          : 'Начисление не войдёт в расчёт; история сохранится. Распределение между тренерами оформите корректировками.'}
        confirmLabel={deciding?.confirm ? 'Подтвердить' : 'Отменить начисление'}
        tone={deciding?.confirm ? 'primary' : 'danger'}
        onClose={() => setDeciding(null)}
        onConfirm={(reason) => run(
          () => mutate.mutateAsync({ id: deciding!.accrual.id, confirm: deciding!.confirm, reason }),
          deciding?.confirm ? 'Начисление подтверждено' : 'Начисление отменено',
        )}
      />
    </>
  )
}

function EstimatesTable() {
  const estimates = useBlockEstimates({ page_size: 200 })
  if (estimates.isLoading) return <LoadingState />
  if (estimates.isError) return <ErrorState onRetry={() => estimates.refetch()} />
  const rows = estimates.data?.results ?? []
  if (rows.length === 0) return <EmptyState title="Открытых блоков нет" />
  return (
    <div className="card overflow-x-auto">
      <p className="border-b border-border p-3 text-xs text-ink-muted">
        Предварительный расчёт по текущим условиям: ученики × цена × процент / 100. Не начисление и не задолженность.
      </p>
      <table className="data-table">
        <thead>
          <tr><th>Тренер</th><th>Группа</th><th>Прогресс</th><th className="text-right">Ученики</th><th className="text-right">Цена</th>
            <th className="text-right">%</th><th className="text-right">Ожидается</th><th>Ожид. выплата</th><th>Статус</th></tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={`${e.cycle_id}-${e.employee ?? 'none'}`}>
              <td className="font-medium text-ink">{e.employee_name || <span className="text-warning">нет правила</span>}</td>
              <td>{e.group_name}<p className="text-xs text-ink-muted">{e.course_name}</p></td>
              <td className="whitespace-nowrap tabular-nums">{e.lessons_done}/{e.required_lessons}</td>
              <td className="text-right">{e.student_count}</td>
              <td className="text-right whitespace-nowrap">{som(e.price_per_student)}</td>
              <td className="text-right">{e.percentage !== null ? `${Number(e.percentage)}%` : '—'}</td>
              <td className="text-right whitespace-nowrap">{som(e.expected_amount)}</td>
              <td className="whitespace-nowrap">{formatDate(e.expected_payment_date)}</td>
              <td>
                <EstimateStatusBadge status={e.status} label={e.status_display} />
                {e.warnings.map((w) => <p key={w} className="mt-1 text-xs text-warning">{w}</p>)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
