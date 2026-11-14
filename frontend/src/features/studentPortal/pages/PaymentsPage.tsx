import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle, Banknote, CalendarClock, CheckCircle2, CircleDollarSign, Clock, CreditCard, Download, ExternalLink, FileText,
  Landmark, Loader2, Printer, ReceiptText, RotateCcw, ShieldCheck, Wallet, X, XCircle,
} from 'lucide-react'
import { Navigate, useSearchParams } from 'react-router-dom'

import { studentPortalApi } from '@/api/studentPortal'
import type { TransactionFilter } from '@/api/studentPortal'
import { cn } from '@/utils/cn'
import type {
  FinanceStatus, InvoiceStage, PaymentMethod, PortalFinance, PortalInvoice, PortalReceipt, PortalTransaction,
} from '@/types/studentPortal'

import { LIVE_QUERY, PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n } from '../i18n'
import type { TFunction } from '../i18n'
import { Bar, Empty, LoadError, Loading, PageTitle, downloadBlob } from '../ui'

/**
 * «Оплата» — the family's read-only view of the accounting records
 * (backend: portal.services.finance). Every amount is the accounting
 * system's own; receipts are the ones the accountant's system issued (with
 * their own PDF) — a payment without one is shown without a receipt number,
 * and invoices are shown as records (no invoice document exists). Nothing
 * here can change a financial record; there is no online payment.
 */

type Tab = 'pending' | 'history' | 'docs'
const TABS: Tab[] = ['pending', 'history', 'docs']
const FILTERS: TransactionFilter[] = ['all', 'completed', 'refunded', 'cancelled']

const NBSP = ' '
export function som(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  const text = n.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).replace(/ /g, NBSP)
  return `${text}${NBSP}сом`
}

const METHOD_ICON: Record<PaymentMethod, typeof Banknote> = { cash: Banknote, bank: Landmark, card: CreditCard, other: Wallet }

const STATUS_STYLE: Record<FinanceStatus, { tone: string; icon: typeof CheckCircle2 }> = {
  paid: { tone: 'bg-brand-50 text-brand-700 ring-brand-200', icon: CheckCircle2 },
  upcoming: { tone: 'bg-info-soft text-info ring-info/20', icon: CalendarClock },
  due: { tone: 'bg-warning-soft text-warning ring-warning/25', icon: Clock },
  overdue: { tone: 'bg-danger-soft text-danger ring-danger/20', icon: AlertTriangle },
  no_contract: { tone: 'bg-surface-muted text-ink-secondary ring-border', icon: FileText },
}

const STAGE_STYLE: Record<InvoiceStage, string> = {
  awaiting: 'bg-info-soft text-info',
  deadline: 'bg-warning-soft text-warning',
  overdue: 'bg-danger-soft text-danger',
  paid: 'bg-brand-50 text-brand-700',
}

const TX_STYLE = {
  completed: { tone: 'bg-brand-50 text-brand-700', icon: CheckCircle2, amount: 'text-brand-700', sign: '+' },
  refunded: { tone: 'bg-warning-soft text-warning', icon: RotateCcw, amount: 'text-warning', sign: '−' },
  cancelled: { tone: 'bg-surface-muted text-ink-muted ring-1 ring-border', icon: XCircle, amount: 'text-ink-muted line-through', sign: '' },
} as const

function invoiceTitle(t: TFunction, invoice: PortalInvoice) {
  return t(`fin.invoice.${invoice.kind}`, { n: invoice.month_number ?? invoice.package_number ?? '' })
}

function invoiceDue(t: TFunction, date: (iso: string | null | undefined, y?: boolean) => string, invoice: PortalInvoice) {
  if (invoice.due_lesson) return t('fin.invoice.dueLesson', { n: invoice.due_lesson, used: invoice.lessons_used ?? 0 })
  return t('fin.invoice.due', { date: date(invoice.due_date, true) })
}

function Pill({ className, children }: { className: string; children: ReactNode }) {
  return <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold', className)}>{children}</span>
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function Overview({ data }: { data: PortalFinance }) {
  const { t, date } = usePortalI18n()
  const s = data.summary
  const style = STATUS_STYLE[data.status]
  const next = data.next_payment
  const total = s ? (s.contract_price ?? s.invoiced) : null
  const nextAmount = next ? som(next.balance) : ''

  return (
    <>
      <section className="sp-card sp-rise relative overflow-hidden p-5 sm:p-7">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1">
            <span className={cn('inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-bold ring-1', style.tone)}>
              <style.icon className="size-4" aria-hidden />{t(`fin.status.${data.status}`)}
            </span>
            <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ink">
              {t(`fin.statusText.${data.status}`, { amount: nextAmount })}
            </p>
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-muted"><ShieldCheck className="size-3.5" aria-hidden />{t('fin.readOnly')}</p>
          </div>
          {s ? (
            <div className="w-full lg:w-[25rem]">
              <div className="flex items-end justify-between gap-3">
                <span className="text-4xl font-extrabold tabular-nums tracking-tight text-brand-700">
                  {data.percent_paid === null ? '—' : `${data.percent_paid}%`}
                </span>
                <span className="text-right text-sm font-semibold text-ink-secondary">
                  {t('fin.paidOf', { paid: som(s.paid), total: som(total) })}
                </span>
              </div>
              <Bar value={data.percent_paid} className="mt-3 h-3" />
              <p className="mt-2 text-xs font-medium text-ink-muted">{t('fin.remaining', { n: som(s.debt) })}</p>
            </div>
          ) : null}
        </div>
      </section>

      {s ? (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          {[
            // A package tariff has no fixed course price — then the total is what has been charged so far.
            { icon: CircleDollarSign, label: s.contract_price !== null ? t('fin.card.price') : t('pay.invoiced'), value: som(total), hint: null, tone: '' },
            { icon: CheckCircle2, label: t('fin.card.paid'), value: som(s.paid), hint: Number(s.overpayment) > 0 ? t('fin.card.overpay', { n: som(s.overpayment) }) : null, tone: 'text-brand-700' },
            { icon: Wallet, label: t('fin.card.balance'), value: som(s.debt), hint: Number(s.due_now) > 0 ? t('fin.card.dueNow', { n: som(s.due_now) }) : null, tone: s.has_debt ? 'text-ink' : 'text-brand-700' },
            {
              icon: CalendarClock, label: t('fin.card.next'), value: next ? som(next.balance) : '—',
              hint: next ? (next.due_lesson ? t('fin.nextLesson', { n: next.due_lesson, used: next.lessons_used ?? 0 }) : t('fin.nextDue', { date: date(next.due_date, true) })) : t('fin.noNext'),
              tone: next?.stage === 'overdue' ? 'text-danger' : '',
            },
          ].map(({ icon: Icon, label, value, hint, tone }, i) => (
            <div key={label} className="sp-card sp-rise min-w-0 p-4 sm:p-5" style={{ animationDelay: `${i * 40}ms` }}>
              <p className="flex items-center gap-2 text-xs font-semibold text-ink-secondary sm:text-sm">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 sm:size-8"><Icon className="size-4" aria-hidden /></span>
                <span className="min-w-0 leading-tight">{label}</span>
              </p>
              <p className={cn('mt-3 break-words text-lg font-extrabold tabular-nums tracking-tight sm:text-2xl', tone || 'text-ink')}>{value}</p>
              {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
            </div>
          ))}
        </div>
      ) : null}

      {data.contracts.length > 1 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {data.contracts.map((c) => (
            <div key={c.id} className="sp-card p-4">
              <p className="text-sm font-bold text-ink">{c.course}{c.subject ? <span className="font-medium text-ink-secondary"> · {c.subject}</span> : null}</p>
              <p className="mt-1 text-xs text-ink-muted">{c.plan}</p>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-secondary">
                <span>{c.contract_price !== null ? t('fin.card.price') : t('pay.invoiced')}: <b className="text-ink">{som(c.contract_price ?? c.invoiced)}</b></span>
                <span>{t('fin.card.paid')}: <b className="text-brand-700">{som(c.paid)}</b></span>
                <span>{t('fin.card.balance')}: <b className="text-ink">{som(c.debt)}</b></span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </>
  )
}

// ---------------------------------------------------------------------------
// Pending invoices
// ---------------------------------------------------------------------------

function InvoiceCard({ invoice }: { invoice: PortalInvoice }) {
  const { t, date } = usePortalI18n()
  const paidPart = Number(invoice.paid) > 0
  return (
    <li className="sp-card sp-card-hover flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
      <div className="flex min-w-0 items-start gap-3">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', STAGE_STYLE[invoice.stage])}><FileText className="size-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="font-bold text-ink">{invoiceTitle(t, invoice)}</p>
          <p className="truncate text-xs text-ink-secondary">{[invoice.number, invoice.course, invoice.subject].filter(Boolean).join(' · ')}</p>
          <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-ink-muted">
            <span>{t('fin.invoice.issued', { date: date(invoice.issue_date, true) })}</span>
            <span className={invoice.stage === 'overdue' ? 'font-semibold text-danger' : undefined}>{invoiceDue(t, date, invoice)}</span>
            {paidPart ? <span>{t('fin.invoice.paidPart', { paid: som(invoice.paid), amount: som(invoice.amount) })}</span> : null}
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end">
        <span className="text-lg font-extrabold tabular-nums text-ink">{som(invoice.balance)}</span>
        <Pill className={STAGE_STYLE[invoice.stage]}>{t(`fin.stage.${invoice.stage}`)}</Pill>
      </div>
    </li>
  )
}

function PendingSection({ data }: { data: PortalFinance }) {
  const { t } = usePortalI18n()
  if (!data.open_invoices.length) {
    return <div className="sp-card"><Empty illustration title={t('fin.noPending')} /></div>
  }
  return <ul className="space-y-3">{data.open_invoices.map((i) => <InvoiceCard key={i.id} invoice={i} />)}</ul>
}

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

function TransactionRow({ tx, onReceipt }: { tx: PortalTransaction; onReceipt: (id: number) => void }) {
  const { t, date } = usePortalI18n()
  const style = TX_STYLE[tx.status]
  const MethodIcon = METHOD_ICON[tx.method] ?? Wallet
  return (
    <li className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', style.tone)}><style.icon className="size-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-2 font-bold text-ink">
            {t(`fin.tx.${tx.kind}`)}
            <span className="text-xs font-medium text-ink-muted">{date(tx.date, true)}</span>
          </p>
          <p className="truncate text-xs text-ink-secondary">{tx.course ?? '—'}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-muted">
            <span className="inline-flex items-center gap-1"><MethodIcon className="size-3.5" aria-hidden />{t(`fin.method.${tx.method}`)}</span>
            {tx.reference ? <span>№ {tx.reference}</span> : null}
            {tx.cashier ? <span>{t('fin.r.cashier')}: {tx.cashier}</span> : null}
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <div className="text-left sm:text-right">
          <p className={cn('text-base font-extrabold tabular-nums', style.amount)}>{style.sign}{som(tx.amount)}</p>
          <Pill className={cn('mt-1', style.tone)}>{t(`fin.tx.${tx.status}`)}</Pill>
        </div>
        {tx.receipt ? (
          <button type="button" onClick={() => onReceipt(tx.receipt!.id)}
            className="sp-press inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-brand-200 px-3 py-2 text-xs font-bold text-brand-700 hover:bg-brand-50">
            <ReceiptText className="size-4" aria-hidden />{t('fin.receiptNo', { n: tx.receipt.number ?? '' })}
          </button>
        ) : (
          <span className="shrink-0 rounded-xl bg-surface-muted px-3 py-2 text-xs font-semibold text-ink-muted">{t('fin.noReceipt')}</span>
        )}
      </div>
    </li>
  )
}

function HistorySection({ onReceipt }: { onReceipt: (id: number) => void }) {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const [filter, setFilter] = useState<TransactionFilter>('all')
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'payment-transactions', student.id, filter],
    queryFn: () => studentPortalApi.transactions(student.id, filter),
    ...LIVE_QUERY,
  })
  return (
    <>
      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
        {FILTERS.map((f) => (
          <button key={f} type="button" onClick={() => setFilter(f)} aria-pressed={filter === f}
            className={cn('sp-press shrink-0 rounded-full px-4 py-2 text-sm font-semibold ring-1',
              filter === f ? 'bg-ink text-white ring-ink' : 'bg-surface text-ink-secondary ring-border hover:text-ink')}>
            {t(`fin.filter.${f}`)}
          </button>
        ))}
      </div>
      {isPending ? <Loading variant="list" /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : data.results.length === 0 ? (
        <div className="sp-card"><Empty illustration title={t('fin.noHistory')} /></div>
      ) : (
        <ul className="sp-card sp-rise divide-y divide-border/60 p-4 sm:p-5">
          {data.results.map((tx) => <TransactionRow key={tx.id} tx={tx} onReceipt={onReceipt} />)}
        </ul>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Documents & receipts
// ---------------------------------------------------------------------------

function ReceiptCard({ receipt, onOpen }: { receipt: PortalReceipt; onOpen: () => void }) {
  const { t, date } = usePortalI18n()
  const cancelled = receipt.status === 'CANCELLED'
  return (
    <li>
      <button type="button" onClick={onOpen}
        className={cn('sp-card sp-card-hover sp-press flex w-full items-start gap-3 p-4 text-left', cancelled && 'opacity-75')}>
        <span className={cn('flex size-11 shrink-0 items-center justify-center rounded-xl', cancelled ? 'bg-surface-muted text-ink-muted' : 'bg-brand-600 text-white')}>
          <ReceiptText className="size-5" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-sm font-bold text-ink">{receipt.number}</span>
            <Pill className={cancelled ? 'bg-surface-muted text-ink-muted' : 'bg-brand-50 text-brand-700'}>{t(`fin.receiptStatus.${receipt.status}`)}</Pill>
          </span>
          <span className="mt-1 block truncate text-xs text-ink-secondary">
            {t(receipt.kind === 'REFUND' ? 'fin.receipt.refundTitle' : 'fin.receipt.title')} · {date(receipt.received_date, true)} · {receipt.course}
          </span>
          <span className={cn('mt-2 block text-lg font-extrabold tabular-nums', cancelled ? 'text-ink-muted line-through' : 'text-ink')}>{som(receipt.amount)}</span>
        </span>
      </button>
    </li>
  )
}

function DocumentsSection({ onReceipt }: { onReceipt: (id: number) => void }) {
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'payment-documents', student.id],
    queryFn: () => studentPortalApi.paymentDocuments(student.id),
    ...LIVE_QUERY,
  })
  if (isPending) return <Loading variant="list" />
  if (isError || !data) return <LoadError onRetry={() => void refetch()} />
  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-ink"><ReceiptText className="size-4 text-brand-600" aria-hidden />{t('fin.docs.receipts')}</h3>
        {data.receipts.length ? (
          <ul className="grid gap-3 md:grid-cols-2">{data.receipts.map((r) => <ReceiptCard key={r.id} receipt={r} onOpen={() => onReceipt(r.id)} />)}</ul>
        ) : <div className="sp-card"><Empty illustration title={t('fin.noReceipts')} /></div>}
      </section>
      <section>
        <h3 className="mb-1 flex items-center gap-2 text-sm font-bold text-ink"><FileText className="size-4 text-brand-600" aria-hidden />{t('fin.docs.invoices')}</h3>
        <p className="mb-3 text-xs text-ink-muted">{t('fin.docs.invoiceNote')}</p>
        {data.invoices.length ? (
          <ul className="sp-card divide-y divide-border/60 px-4 sm:px-5">
            {data.invoices.map((invoice) => (
              <li key={invoice.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-ink">{invoiceTitle(t, invoice)}</span>
                  <span className="block text-xs text-ink-muted">{[invoice.number, t('fin.invoice.issued', { date: date(invoice.issue_date, true) })].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-sm font-bold tabular-nums text-ink">{som(invoice.amount)}</span>
                  <Pill className={STAGE_STYLE[invoice.stage]}>{t(`fin.stage.${invoice.stage}`)}</Pill>
                </span>
              </li>
            ))}
          </ul>
        ) : <Empty>{t('fin.noInvoices')}</Empty>}
      </section>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Receipt viewer — structured data + the accounting PDF (preview / download / print)
// ---------------------------------------------------------------------------

function printBlob(blob: Blob) {
  const url = URL.createObjectURL(blob)
  const frame = document.createElement('iframe')
  frame.style.position = 'fixed'
  frame.style.width = '0'
  frame.style.height = '0'
  frame.style.border = '0'
  frame.src = url
  frame.onload = () => {
    try {
      frame.contentWindow?.focus()
      frame.contentWindow?.print()
    } catch {
      window.open(url, '_blank', 'noopener')
    }
    window.setTimeout(() => { frame.remove(); URL.revokeObjectURL(url) }, 60_000)
  }
  document.body.appendChild(frame)
}

function ReceiptViewer({ receiptId, onClose }: { receiptId: number; onClose: () => void }) {
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'receipt', student.id, receiptId],
    queryFn: () => studentPortalApi.receipt(student.id, receiptId),
  })
  const pdf = useQuery({
    queryKey: [...PORTAL_KEY, 'receipt-pdf', student.id, receiptId],
    queryFn: () => studentPortalApi.receiptPdf(student.id, receiptId),
    staleTime: Infinity,
  })
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!pdf.data) return
    const url = URL.createObjectURL(pdf.data)
    setPdfUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [pdf.data])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = overflow }
  }, [onClose])

  const filename = `receipt-${data?.number ?? receiptId}.pdf`
  const download = async () => downloadBlob(pdf.data ?? await studentPortalApi.receiptPdf(student.id, receiptId, true), filename)
  const print = async () => printBlob(pdf.data ?? await studentPortalApi.receiptPdf(student.id, receiptId))

  const rows: [string, ReactNode][] = data ? [
    [t('fin.r.student'), data.student],
    [t('fin.r.course'), data.course],
    [t('fin.r.group'), data.group],
    ...(data.payer ? [[t('fin.r.payer'), data.payer] as [string, ReactNode]] : []),
    [t('fin.r.purpose'), data.purpose_lines.length ? data.purpose_lines.join('; ') : data.purpose],
    [t('fin.r.date'), date(data.received_date, true)],
    [t('fin.r.method'), t(`fin.method.${data.method}`)],
    ...(data.reference ? [[t('fin.r.reference'), data.reference] as [string, ReactNode]] : []),
    ...(data.has_balances ? [
      [t('fin.r.previously'), som(data.previously_paid)] as [string, ReactNode],
      [t('fin.r.outstanding'), som(data.outstanding)] as [string, ReactNode],
      ...(Number(data.credit) > 0 ? [[t('fin.r.credit'), som(data.credit)] as [string, ReactNode]] : []),
    ] : []),
    [t('fin.r.cashier'), data.cashier || '—'],
    [t('fin.r.issued'), date(data.issued_at, true)],
  ] : []

  return (
    <div className="sp-root fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-6" role="dialog" aria-modal="true" aria-label={data?.number ?? t('fin.receipt.title')}>
      <button type="button" className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" aria-label={t('fin.close')} onClick={onClose} />
      <div className="sp-sheet relative max-h-[92dvh] w-full overflow-y-auto rounded-t-3xl bg-surface shadow-2xl sm:max-h-[88dvh] sm:w-[min(64rem,100%)] sm:rounded-3xl">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border/60 bg-surface/95 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-ink-secondary">{t(data?.kind === 'REFUND' ? 'fin.receipt.refundTitle' : 'fin.receipt.title')}</p>
            <p className="truncate font-mono text-lg font-extrabold text-ink">{data?.number ?? '…'}</p>
          </div>
          <button type="button" onClick={onClose} className="sp-press rounded-xl p-2 text-ink-secondary hover:bg-surface-hover hover:text-ink" aria-label={t('fin.close')}>
            <X className="size-5" aria-hidden />
          </button>
        </div>

        {isPending ? <div className="p-5"><Loading variant="list" /></div> : isError || !data ? <div className="p-5"><LoadError onRetry={() => void refetch()} /></div> : (
          <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <div>
              <div className="flex items-end justify-between gap-3 rounded-2xl bg-brand-50/70 p-4">
                <div>
                  <p className="text-xs font-semibold text-brand-700">{t('fin.r.amount')}</p>
                  <p className={cn('text-3xl font-extrabold tabular-nums tracking-tight', data.status === 'CANCELLED' ? 'text-ink-muted line-through' : 'text-ink')}>{som(data.amount)}</p>
                </div>
                <Pill className={data.status === 'CANCELLED' ? 'bg-surface-muted text-ink-muted ring-1 ring-border' : 'bg-brand-600 text-white'}>
                  {t(`fin.receiptStatus.${data.status}`)}
                </Pill>
              </div>
              {data.status === 'CANCELLED' ? (
                <p className="mt-3 flex items-start gap-2 rounded-2xl bg-danger-soft px-3.5 py-2.5 text-xs text-danger"><XCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t('fin.receipt.cancelled')}</p>
              ) : null}
              <dl className="mt-4 divide-y divide-border/60">
                {rows.map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4 py-2.5 text-sm">
                    <dt className="shrink-0 text-ink-secondary">{label}</dt>
                    <dd className="min-w-0 text-right font-semibold text-ink">{value || '—'}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-ink-muted"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t('fin.receipt.notFiscal')}</p>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
                <button type="button" onClick={() => void download()} className="sp-press inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-brand-700">
                  <Download className="size-4" aria-hidden />{t('fin.download')}
                </button>
                <button type="button" onClick={() => void print()} className="sp-press inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-bold text-ink hover:bg-surface-hover">
                  <Printer className="size-4" aria-hidden />{t('fin.print')}
                </button>
                {pdfUrl ? (
                  <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="sp-press col-span-2 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-brand-700 hover:bg-brand-50 lg:hidden">
                    <ExternalLink className="size-4" aria-hidden />{t('fin.openPdf')}
                  </a>
                ) : null}
              </div>
            </div>
            {/* PDF preview: desktop only — phones open the PDF in their own viewer. */}
            <div className="hidden min-h-[32rem] overflow-hidden rounded-2xl border border-border/70 bg-surface-muted lg:block">
              {pdfUrl ? (
                <iframe src={pdfUrl} title={data.number ?? 'receipt'} className="h-full min-h-[32rem] w-full" />
              ) : pdf.isError ? (
                <p className="p-6 text-center text-sm text-ink-muted">{t('fin.pdfError')}</p>
              ) : (
                <p className="flex h-full items-center justify-center gap-2 text-sm text-ink-muted"><Loader2 className="size-4 animate-spin" aria-hidden />{t('fin.loadingPdf')}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function StudentPaymentsPage() {
  const { student, me } = usePortal()
  const { t } = usePortalI18n()
  const [params, setParams] = useSearchParams()
  const tab: Tab = TABS.includes(params.get('tab') as Tab) ? (params.get('tab') as Tab) : 'pending'
  const [receiptId, setReceiptId] = useState<number | null>(null)
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: [...PORTAL_KEY, 'payments', student.id],
    queryFn: () => studentPortalApi.payments(student.id),
    enabled: me.can_view_payments,
    ...LIVE_QUERY,
  })
  if (!me.can_view_payments) return <Navigate to="/student" replace />

  const tabLabel: Record<Tab, string> = {
    pending: t('fin.section.pending'), history: t('fin.section.history'), docs: t('fin.section.docs'),
  }
  return (
    <div>
      <PageTitle title={t('pay.title')} subtitle={t('fin.subtitle')} />
      {isPending ? <Loading /> : isError || !data ? <LoadError onRetry={() => void refetch()} /> : (
        <div className="space-y-5">
          <Overview data={data} />
          <div className="sticky top-[3.6rem] z-20 -mx-4 bg-[#f6f8f6]/90 px-4 py-2 backdrop-blur sm:mx-0 sm:px-0 lg:static lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
            <div className="flex w-full gap-1 overflow-x-auto rounded-2xl bg-surface p-1 shadow-sm ring-1 ring-border/70 sm:w-fit" role="tablist">
              {TABS.map((v) => (
                <button key={v} type="button" role="tab" aria-selected={tab === v}
                  onClick={() => setParams(v === 'pending' ? {} : { tab: v }, { replace: true })}
                  className={cn('sp-press inline-flex flex-1 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-bold sm:flex-none',
                    tab === v ? 'bg-brand-600 text-white shadow-sm' : 'text-ink-secondary hover:text-ink')}>
                  {tabLabel[v]}
                  {v === 'pending' && data.open_invoices.length ? (
                    <span className={cn('rounded-full px-1.5 text-[11px]', tab === v ? 'bg-white/25' : 'bg-danger-soft text-danger')}>{data.open_invoices.length}</span>
                  ) : null}
                </button>
              ))}
            </div>
          </div>
          {tab === 'pending' ? <PendingSection data={data} /> : tab === 'history' ? <HistorySection onReceipt={setReceiptId} /> : <DocumentsSection onReceipt={setReceiptId} />}
        </div>
      )}
      {receiptId !== null ? <ReceiptViewer receiptId={receiptId} onClose={() => setReceiptId(null)} /> : null}
    </div>
  )
}
