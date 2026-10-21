import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Download, Printer } from 'lucide-react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import type { Receipt } from '@/types/finance'
import { cn } from '@/utils/cn'

import { FINANCE_KEY, Loadable, formatDateTime, som, useFinanceMe, useRunner } from './ui'

/** Печатный чек Okurmen Kids: настоящий логотип, данные — снимок операции.
 * Повторное открытие и печать ничего не создают. Не фискальный документ. */
export function ReceiptPage() {
  const { receiptId } = useParams()
  const [params] = useSearchParams()
  const id = Number(receiptId)
  const me = useFinanceMe()
  const { run } = useRunner()
  const [size, setSize] = useState<'a4' | 'compact'>('a4')
  const query = useQuery({ queryKey: [...FINANCE_KEY, 'receipt', id], queryFn: () => financeApi.receipt(id) })
  const autoPrinted = useRef(false)

  async function print() {
    if (me.data?.can_record_payments) await financeApi.receiptPrinted(id).catch(() => undefined)
    window.print()
  }

  useEffect(() => {
    if (query.data && params.get('print') === '1' && !autoPrinted.current) {
      autoPrinted.current = true
      setTimeout(() => void print(), 300)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.data])

  return (
    <div>
      <div className="print:hidden">
        <BackLink to="/finance/receipts">Все чеки</BackLink>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <SegmentedControl aria-label="Формат" value={size} onChange={setSize}
            options={[{ value: 'a4', label: 'A4' }, { value: 'compact', label: 'Чековый принтер 80 мм' }]} />
          <Button leftIcon={<Printer className="size-4" />} onClick={print}>Печать</Button>
          <Button variant="secondary" leftIcon={<Download className="size-4" />}
            onClick={() => run(() => financeApi.downloadReceiptPdf(id, size))}>Скачать PDF</Button>
        </div>
      </div>
      <Loadable query={query}>{(receipt) => <ReceiptSheet receipt={receipt} compact={size === 'compact'} />}</Loadable>
      <style>{`@media print { @page { size: ${size === 'compact' ? '80mm auto' : 'A4'}; margin: ${size === 'compact' ? '4mm' : '15mm'}; }
        aside, header, nav { display: none !important; } main { padding: 0 !important; } body { background: #fff !important; } }`}</style>
    </div>
  )
}

export function ReceiptSheet({ receipt, compact }: { receipt: Receipt; compact?: boolean }) {
  const amount = receipt.rows.find((r) => r.label.startsWith('Сумма'))
  return (
    <article className={cn('receipt mx-auto bg-white text-[#202622] shadow-sm print:shadow-none',
      compact ? 'w-[80mm] p-4 text-[11px]' : 'max-w-[180mm] rounded-xl border border-border p-8 text-sm print:border-0 print:p-0')}
      aria-label={`Чек ${receipt.number}`}>
      <header className="flex items-center gap-3 border-b border-[#e1e7e2] pb-3">
        <img src={logo} alt="Okurmen Kids" className={compact ? 'size-10 object-contain' : 'size-14 object-contain'} />
        <div>
          <p className={cn('font-bold', compact ? 'text-base' : 'text-xl')}>{receipt.academy.name}</p>
          {receipt.academy.details ? <p className="whitespace-pre-line text-[#68736c]">{receipt.academy.details}</p> : null}
        </div>
      </header>
      <div className="mt-3 flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{receipt.kind === 'REFUND' ? 'Чек возврата' : 'Чек об оплате'} № {receipt.number}</p>
          <p className="text-[#68736c]">{formatDateTime(receipt.issued_at)}</p>
        </div>
        {receipt.status === 'CANCELLED' ? <Badge tone="danger">Аннулирован</Badge> : null}
      </div>
      <p className={cn('mt-3 font-bold text-[#2f8f5b]', compact ? 'text-xl' : 'text-3xl')}>{amount?.value ?? som(receipt.amount)}</p>
      <dl className="mt-3">
        {receipt.rows.filter((r) => r !== amount).map((r) => (
          <div key={r.label} className="grid grid-cols-[40%_60%] gap-2 border-b border-[#e1e7e2] py-1.5 last:border-0">
            <dt className="text-[#68736c]">{r.label}</dt>
            <dd className="font-medium">{r.value}</dd>
          </div>
        ))}
      </dl>
      {receipt.status === 'CANCELLED' && receipt.cancel_reason ? (
        <p className="mt-3 rounded bg-[#fdecec] p-2 font-medium">Чек аннулирован: {receipt.cancel_reason}</p>
      ) : null}
      <footer className="mt-4 space-y-1 text-[#68736c]">
        {receipt.academy.footer ? <p>{receipt.academy.footer}</p> : null}
        <p className="text-xs">Внутренний документ академии об оплате обучения. Не является фискальным чеком.</p>
      </footer>
    </article>
  )
}

export function ReceiptsPage() {
  const navigate = useNavigate()
  const { run } = useRunner()
  const [search, setSearch] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'receipts', search, from, to, page],
    queryFn: () => financeApi.receipts({ search: search || undefined, date_from: from || undefined, date_to: to || undefined, page }),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <PageHeader title="Чеки" description="Каждый платёж и возврат имеет чек с уникальным номером. Повторная печать не создаёт новых операций." />
      <FilterBar>
        <FilterField size="lg"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Номер чека, студент, плательщик" /></FilterField>
        <FilterField label="С" htmlFor="rc-from"><Input id="rc-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></FilterField>
        <FilterField label="По" htmlFor="rc-to"><Input id="rc-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></FilterField>
      </FilterBar>
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle="Чеков пока нет">
          {(data) => (
            <>
              <DataTable rows={data.results} getRowKey={(r) => r.id} onRowClick={(r) => navigate(`/finance/receipts/${r.id}`)} columns={[
                { key: 'n', header: 'Номер', render: (r) => <span className="font-medium">{r.number}</span> },
                { key: 'd', header: 'Дата', render: (r) => formatDateTime(r.issued_at) },
                { key: 's', header: 'Студент', render: (r) => r.student_name },
                { key: 'k', header: 'Операция', render: (r) => r.kind_display },
                { key: 'a', header: 'Сумма', render: (r) => <span className="tabular-nums">{r.kind === 'REFUND' ? '−' : ''}{som(r.amount)}</span> },
                { key: 'st', header: 'Статус', render: (r) => <Badge tone={r.status === 'ISSUED' ? 'success' : 'muted'}>{r.status_display}</Badge> },
                { key: 'p', header: 'Печатей', render: (r) => r.print_count },
                { key: 'act', header: '', className: 'text-right', render: (r) => (
                  <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()} role="presentation">
                    <Button size="sm" variant="ghost" aria-label="Печать" onClick={() => navigate(`/finance/receipts/${r.id}?print=1`)}><Printer className="size-4" /></Button>
                    <Button size="sm" variant="ghost" aria-label="PDF" onClick={() => run(() => financeApi.downloadReceiptPdf(r.id))}><Download className="size-4" /></Button>
                  </div>
                ) },
              ]} />
              <div className="mt-3"><Pagination page={page} pageSize={50} totalCount={data.count} onPageChange={setPage} /></div>
            </>
          )}
        </Loadable>
      </div>
    </div>
  )
}

