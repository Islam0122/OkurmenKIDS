import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import { Empty, LoadError, Loading, PCard, PageTitle, Stat } from '../ui'

export function StudentPaymentsPage() {
  const { student, me } = usePortal()
  const { t, date } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'payments', student.id],
    queryFn: () => studentPortalApi.payments(student.id),
    enabled: me.can_view_payments,
  })
  if (!me.can_view_payments) return <Navigate to="/student" replace />
  if (isPending) return <Loading />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  const som = (v: string | null) => (v === null ? '—' : `${Number(v).toLocaleString('ru-RU')} ${t('common.som')}`)
  const s = data.summary
  return (
    <div>
      <PageTitle title={t('pay.title')} />
      {!s ? <Empty>{t('pay.noContracts')}</Empty> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label={t('pay.price')} value={som(s.contract_price)} />
            <Stat label={t('pay.paid')} value={som(s.paid)} accent />
            <Stat label={t('pay.dueNow')} value={som(s.due_now)} />
            <Stat label={s.has_debt ? t('pay.debt') : t('pay.overpayment')} value={som(s.has_debt ? s.debt : s.overpayment)} />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <PCard title={t('pay.open')}>
              {data.open_invoices.length === 0 ? <Empty>{t('dash.allPaid')}</Empty> : (
                <ul className="divide-y divide-border/70">
                  {data.open_invoices.map((invoice) => (
                    <li key={invoice.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <span className="min-w-0">
                        <span className="block font-medium text-ink">{invoice.number ?? `#${invoice.id}`}{invoice.subject ? ` · ${invoice.subject}` : ''}</span>
                        {invoice.overdue_since ? <span className="text-xs text-danger">{date(invoice.overdue_since, true)}</span> : null}
                      </span>
                      <span className="text-right">
                        <span className="block font-semibold tabular-nums text-ink">{som(invoice.amount)}</span>
                        <span className="text-xs text-ink-muted">{t('pay.balance', { n: som(invoice.balance) })}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </PCard>
            <PCard title={t('pay.history')}>
              {data.history.length === 0 ? <Empty>{t('pay.noHistory')}</Empty> : (
                <ul className="divide-y divide-border/70">
                  {data.history.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <span>
                        <span className="block font-medium text-ink">{p.kind === 'refund' ? t('pay.refund') : t('pay.payment')}</span>
                        <span className="text-xs text-ink-muted">{date(p.date, true)}</span>
                      </span>
                      <span className={p.kind === 'refund' ? 'font-semibold tabular-nums text-danger' : 'font-semibold tabular-nums text-brand-700'}>
                        {p.kind === 'refund' ? '−' : '+'}{som(p.amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </PCard>
          </div>
        </div>
      )}
    </div>
  )
}
