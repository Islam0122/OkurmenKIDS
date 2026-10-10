import { FileDown } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useMyPayrolls } from '@/hooks/useAccounting'

import { PayrollStatusBadge, formatDate, som, useRunner } from './shared'

/** Личный кабинет сотрудника: только собственные утверждённые начисления и выплаты. */
export function MySalaryPage() {
  const payrolls = useMyPayrolls()
  const { run } = useRunner()

  return (
    <div>
      <PageHeader title="Мои начисления" description="Утверждённые начисления и выплаты по расчётным периодам." />
      {payrolls.isLoading ? <LoadingState /> : payrolls.isError ? <ErrorState onRetry={() => payrolls.refetch()} /> :
        payrolls.data?.results.length === 0 ? <EmptyState title="Утверждённых начислений пока нет" /> : (
          <div className="space-y-4">
            {payrolls.data?.results.map((p) => (
              <div key={p.id} className="card p-4 sm:p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold text-ink">{p.period_label}</p>
                    <p className="text-sm text-ink-secondary">
                      Начислено {som(p.total)} · выплачено {som(p.total_paid)} · остаток {som(p.amount_due)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <PayrollStatusBadge status={p.status} label={p.status_display} />
                    <Button size="sm" variant="ghost" leftIcon={<FileDown className="size-4" />}
                      onClick={() => run(() => accountingApi.downloadMyPayrollPdf(p.id))}>PDF</Button>
                  </div>
                </div>
                <ul className="mt-3 space-y-1 text-sm">
                  {p.lines.map((l) => (
                    <li key={l.id} className="flex justify-between gap-3"><span>{l.description}</span><span className="whitespace-nowrap">{som(l.amount)}</span></li>
                  ))}
                  {p.adjustments.filter((a) => a.status === 'APPLIED').map((a) => (
                    <li key={`a${a.id}`} className="flex justify-between gap-3 text-ink-secondary">
                      <span>{a.kind_display}: {a.reason}</span><span className="whitespace-nowrap">{som(a.amount)}</span>
                    </li>
                  ))}
                </ul>
                {p.payments.filter((pay) => pay.status === 'CONFIRMED').length ? (
                  <p className="mt-2 text-xs text-ink-muted">
                    Выплаты: {p.payments.filter((pay) => pay.status === 'CONFIRMED').map((pay) => `${formatDate(pay.payment_date)} — ${som(pay.amount)}`).join(', ')}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )}
    </div>
  )
}
