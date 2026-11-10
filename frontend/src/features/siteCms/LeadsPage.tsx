import { useState } from 'react'
import { MessageCircle, Phone, Send } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Tabs } from '@/components/ui/Tabs'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, useSiteMeta, type Row } from './api'

const PAGE_SIZE = 30
const METHOD_ICON = { phone: Phone, whatsapp: MessageCircle, telegram: Send } as const
const digits = (phone: string) => phone.replace(/\D/g, '')

/** /marketing/site/leads — заявки «Записать ребёнка» и регистрации на мероприятия с сайта. */
export function LeadsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'registrations' ? 'registrations' : 'leads'
  return (
    <div className="space-y-4">
      <PageHeader title="Заявки с сайта" description="Заявки на обучение и регистрации на мероприятия. Повторная заявка с того же телефона за 24 часа не создаёт дубль — она добавляется к первой." />
      <Tabs aria-label="Тип заявок" items={[{ key: 'leads', label: 'На обучение' }, { key: 'registrations', label: 'На мероприятия' }] as const} value={tab}
        onChange={(key) => setParams(key === 'leads' ? {} : { tab: key })} />
      <Inbox key={tab} resource={tab} />
    </div>
  )
}

function Inbox({ resource }: { resource: 'leads' | 'registrations' }) {
  const meta = useSiteMeta()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const query = useSiteList(resource, { search: search || undefined, status: status || undefined, page, page_size: PAGE_SIZE, ordering: '-created_at' })
  const { rows, count } = toList(query.data)
  const statuses = meta.data?.choices[resource === 'leads' ? 'lead_status' : 'registration_status'] ?? []
  return (
    <>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Имя или телефон" /></div>
        <div className="sm:w-52"><Select aria-label="Статус" value={status} placeholder="Все статусы" options={statuses} onChange={(e) => { setStatus(e.target.value); setPage(1) }} /></div>
      </div>
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : rows.length ? (
        <>
          <ul className="space-y-2">
            {rows.map((row) => <LeadRow key={row.id} row={row} resource={resource} statuses={statuses} />)}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : <EmptyState title="Заявок нет" description="Новые заявки с сайта появятся здесь." />}
    </>
  )
}

function LeadRow({ row, resource, statuses }: { row: Row; resource: 'leads' | 'registrations'; statuses: { value: string; label: string }[] }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [note, setNote] = useState(String(row.note ?? ''))
  const save = async (body: Record<string, unknown>) => {
    try {
      await siteCmsApi.save(resource, row.id, body)
      await invalidate()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  const phone = String(row.phone)
  const method = (row.contact_method as keyof typeof METHOD_ICON) ?? 'phone'
  const Icon = METHOD_ICON[method] ?? Phone
  const contactHref = method === 'whatsapp' ? `https://wa.me/${digits(phone)}` : method === 'telegram' ? `https://t.me/+${digits(phone)}` : `tel:${phone}`
  const details = resource === 'leads'
    ? [row.child_age ? `ребёнку ${row.child_age} лет` : '', row.course_title, row.branch_name, Number(row.repeat_count) ? `повторов: ${row.repeat_count}` : ''].filter(Boolean)
    : [row.event_title, row.child_name, row.child_age ? `${row.child_age} лет` : ''].filter(Boolean)
  return (
    <li className="rounded-xl border border-border bg-surface p-3 sm:p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{String(row.parent_name)}</p>
          <a href={contactHref} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline">
            <Icon className="size-4" aria-hidden /> {phone}
          </a>
          <p className="mt-1 text-sm text-ink-secondary">{details.join(' · ')}</p>
          {row.message || row.comment ? <p className="mt-2 rounded-lg bg-surface-muted px-3 py-2 text-sm whitespace-pre-line text-ink">{String(row.message || row.comment)}</p> : null}
          {resource === 'leads' ? (
            <Textarea aria-label="Заметка" rows={1} value={note} onChange={(e) => setNote(e.target.value)} onBlur={() => note !== (row.note ?? '') && save({ note })} placeholder="Заметка менеджера" className="mt-2 text-sm" />
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2 sm:flex-col sm:items-end">
          <Select aria-label="Статус" value={String(row.status)} options={statuses} onChange={(e) => save({ status: e.target.value })} className="w-40" />
          <span className="text-xs text-ink-muted">{new Date(String(row.created_at)).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</span>
          {row.utm_source ? <span className="text-xs text-ink-muted">utm: {String(row.utm_source)}{row.utm_campaign ? ` / ${row.utm_campaign}` : ''}</span> : null}
        </div>
      </div>
    </li>
  )
}
