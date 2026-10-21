import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus, Printer } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { financeApi } from '@/api/finance'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DataTable } from '@/components/ui/DataTable'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'

import { Amount, FINANCE_KEY, Loadable, formatDate, useFinanceMe, useFinanceOptions } from './ui'

export function PaymentsPage() {
  const navigate = useNavigate()
  const me = useFinanceMe()
  const options = useFinanceOptions()
  const [f, setF] = useState({ search: '', method: '', kind: '', status: '', program: '', group: '', date_from: '', date_to: '', page: 1 })
  const set = (patch: Partial<typeof f>) => setF({ ...f, ...patch, page: patch.page ?? 1 })
  const query = useQuery({
    queryKey: [...FINANCE_KEY, 'payments', f],
    queryFn: () => financeApi.payments(Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))),
    placeholderData: keepPreviousData,
  })
  return (
    <div>
      <PageHeader title="Платежи" description="Фактически полученные деньги и возвраты. Платёж не удаляется и не редактируется — только сторно с причиной."
        actions={me.data?.can_record_payments ? (
          <Button leftIcon={<Plus className="size-4" />} onClick={() => navigate('/finance/payments/new')}>Добавить платёж</Button>
        ) : undefined} />
      <FilterBar>
        <FilterField size="lg"><SearchInput value={f.search} onChange={(search) => set({ search })} placeholder="Студент или номер документа" /></FilterField>
        <FilterField>
          <Select aria-label="Программа" value={f.program} placeholder="Все программы" onChange={(e) => set({ program: e.target.value })}
            options={(options.data?.programs ?? []).map((p) => ({ value: String(p.id), label: p.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Группа" value={f.group} placeholder="Все группы" onChange={(e) => set({ group: e.target.value })}
            options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} />
        </FilterField>
        <FilterField>
          <Select aria-label="Способ" value={f.method} placeholder="Все способы" onChange={(e) => set({ method: e.target.value })}
            options={options.data?.payment_methods ?? []} />
        </FilterField>
        <FilterField>
          <Select aria-label="Тип" value={f.kind} placeholder="Платежи и возвраты" onChange={(e) => set({ kind: e.target.value })}
            options={[{ value: 'payment', label: 'Платежи' }, { value: 'refund', label: 'Возвраты' }]} />
        </FilterField>
        <FilterField>
          <Select aria-label="Статус" value={f.status} placeholder="Все статусы" onChange={(e) => set({ status: e.target.value })}
            options={[{ value: 'confirmed', label: 'Проведённые' }, { value: 'void', label: 'Сторнированные' }]} />
        </FilterField>
        <FilterField label="С" htmlFor="pm-from"><Input id="pm-from" type="date" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} /></FilterField>
        <FilterField label="По" htmlFor="pm-to"><Input id="pm-to" type="date" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} /></FilterField>
      </FilterBar>
      <div className="mt-4">
        <Loadable query={query} empty={(d) => d.count === 0} emptyTitle="Платежей не найдено">
          {(data) => (
            <>
              <DataTable rows={data.results} getRowKey={(p) => p.id} onRowClick={(p) => navigate(`/finance/students/${p.billing_profile}#payments`)} columns={[
                { key: 'd', header: 'Дата', render: (p) => formatDate(p.received_date) },
                { key: 's', header: 'Студент', render: (p) => (
                  <div><p className="font-medium">{p.student_name}</p><p className="text-xs text-ink-secondary">{p.group_name} · {p.program_name}</p></div>
                ) },
                { key: 'pur', header: 'Назначение', render: (p) => p.kind === 'refund' ? 'Возврат' : (p.purpose_display || 'Оплата обучения') },
                { key: 'a', header: 'Сумма', render: (p) => <Amount value={p.kind === 'refund' ? `-${p.amount}` : p.amount} /> },
                { key: 'free', header: 'В аванс', render: (p) => <Amount value={p.unallocated} tone="muted" /> },
                { key: 'm', header: 'Способ', render: (p) => p.method_display },
                { key: 'st', header: 'Статус', render: (p) => p.status === 'void' ? <Badge tone="muted">Сторно</Badge> : <Badge tone="success">Проведён</Badge> },
                { key: 'who', header: 'Принял', render: (p) => p.created_by_name ?? '—' },
                { key: 'r', header: 'Чек', render: (p) => p.receipt ? (
                  <Button size="sm" variant="ghost" leftIcon={<Printer className="size-4" />}
                    onClick={(e) => { e.stopPropagation(); navigate(`/finance/receipts/${p.receipt!.id}`) }}>{p.receipt.number}</Button>
                ) : '—' },
              ]} />
              <div className="mt-3"><Pagination page={f.page} pageSize={50} totalCount={data.count} onPageChange={(page) => set({ page })} /></div>
            </>
          )}
        </Loadable>
      </div>
    </div>
  )
}
