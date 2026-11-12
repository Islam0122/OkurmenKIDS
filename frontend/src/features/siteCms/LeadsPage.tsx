import { useEffect, useState } from 'react'
import { Clock, KanbanSquare, List, MessageCircle, Phone, Send, UserCheck } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { apiClient } from '@/api/client'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, toList, useSiteInvalidate, useSiteList, useSiteMeta, type Choice, type Row, type SiteMeta } from './api'
import { CMS_BASE, CmsPage, formatDate, ListSkeleton, relativeTime, Skeleton } from './ui'

const PAGE_SIZE = 30
const METHOD_ICON = { phone: Phone, whatsapp: MessageCircle, telegram: Send } as const
const digits = (phone: string) => phone.replace(/\D/g, '')

/** Lead statuses as a pipeline: colors of the CRM. */
export const LEAD_TONE: Record<string, { dot: string; chip: string }> = {
  new: { dot: 'bg-cms-gold', chip: 'bg-cms-gold-soft text-cms-gold-deep' },
  processing: { dot: 'bg-info', chip: 'bg-info-soft text-info' },
  contacted: { dot: 'bg-brand-500', chip: 'bg-brand-50 text-brand-700' },
  trial: { dot: 'bg-violet-400', chip: 'bg-violet-50 text-violet-700' },
  enrolled: { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700' },
  rejected: { dot: 'bg-ink-muted', chip: 'bg-surface-hover text-ink-muted' },
  confirmed: { dot: 'bg-brand-500', chip: 'bg-brand-50 text-brand-700' },
  attended: { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700' },
  cancelled: { dot: 'bg-ink-muted', chip: 'bg-surface-hover text-ink-muted' },
}

const contactHref = (row: Row) => {
  const phone = String(row.phone)
  const method = String(row.contact_method ?? 'phone')
  return method === 'whatsapp' ? `https://wa.me/${digits(phone)}` : method === 'telegram' ? `https://t.me/+${digits(phone)}` : `tel:${phone}`
}

function useLeadSummary() {
  return useQuery({
    queryKey: ['site-cms', 'leads', 'summary'],
    queryFn: () => apiClient.get<{ by_status: Record<string, number>; last_7_days: number }>('/marketing/site/leads/summary/').then((r) => r.data),
  })
}

export function StatusChip({ status, statuses }: { status: string; statuses: Choice[] }) {
  const tone = LEAD_TONE[status] ?? LEAD_TONE.rejected
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs leading-none font-medium whitespace-nowrap', tone.chip)}>
      <span className={cn('size-1.5 rounded-full', tone.dot)} aria-hidden />{statuses.find((s) => s.value === status)?.label ?? status}
    </span>
  )
}

/** /marketing/site/leads — заявки «Записать ребёнка» и регистрации на мероприятия. */
export function LeadsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'registrations' ? 'registrations' : 'leads'
  const summary = useLeadSummary()
  return (
    <CmsPage title="Заявки с сайта" description="Повторная заявка с того же телефона за 24 часа не создаёт дубль — она добавляется к первой."
      actions={<Link to={`${CMS_BASE}/leads/board`} className="inline-flex h-10 items-center gap-2 rounded-lg border border-brand-200 bg-surface px-4 text-sm font-medium text-brand-700 hover:bg-brand-50"><KanbanSquare className="size-4" aria-hidden />Доска статусов</Link>}>
      <div role="tablist" aria-label="Тип заявок" className="flex gap-1 border-b border-border">
        {([['leads', 'На обучение', summary.data?.by_status.new], ['registrations', 'На мероприятия', undefined]] as const).map(([key, label, n]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setParams(key === 'leads' ? {} : { tab: key })}
            className={cn('-mb-px inline-flex h-11 items-center gap-2 border-b-2 px-3 text-sm font-medium', tab === key ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-secondary hover:text-ink')}>
            {label}{n ? <span className="rounded-full bg-cms-gold px-1.5 py-0.5 text-[0.6875rem] leading-none font-bold text-brand-700">{n}</span> : null}
          </button>
        ))}
      </div>
      {tab === 'leads' ? <LeadInbox /> : <RegistrationInbox />}
    </CmsPage>
  )
}

function LeadInbox() {
  const meta = useSiteMeta()
  const summary = useLeadSummary()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [course, setCourse] = useState('')
  const [assignee, setAssignee] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const editor = Boolean(meta.data?.permissions.can_edit)
  const courses = useSiteList('courses', { page_size: 200 }, editor)
  const query = useSiteList('leads', { search: search || undefined, status: status || undefined, course: course || undefined, assigned_to: assignee || undefined, page, page_size: PAGE_SIZE, ordering: '-created_at' })
  const { rows, count } = toList(query.data)
  const statuses = meta.data?.choices.lead_status ?? []
  const staff = meta.data?.staff ?? []
  const openRow = rows.find((r) => r.id === open) ?? null

  return (
    <div className="space-y-4">
      {/* Pipeline counters — click to filter */}
      <ul className="scroll-x -mx-4 flex gap-2 px-4 sm:mx-0 sm:grid sm:grid-cols-3 sm:px-0 lg:grid-cols-6">
        {statuses.map((s) => {
          const n = summary.data?.by_status[s.value] ?? 0
          const on = status === s.value
          return (
            <li key={s.value} className="shrink-0">
              <button type="button" aria-pressed={on} onClick={() => { setStatus(on ? '' : s.value); setPage(1) }}
                className={cn('flex w-36 flex-col rounded-xl border bg-surface px-3 py-2.5 text-left transition sm:w-full', on ? 'border-brand-500 ring-1 ring-brand-500' : 'border-border hover:border-brand-200')}>
                <span className="flex items-center gap-1.5 text-xs font-medium text-ink-secondary"><span className={cn('size-2 rounded-full', LEAD_TONE[s.value]?.dot)} aria-hidden />{s.label}</span>
                <span className="mt-1 font-display text-xl font-bold text-ink tabular-nums">{summary.isPending ? <Skeleton className="h-6 w-8" /> : n}</span>
              </button>
            </li>
          )
        })}
      </ul>

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Имя, телефон, комментарий" /></div>
        <div className="sm:w-48"><Select aria-label="Статус" value={status} placeholder="Все статусы" options={statuses} onChange={(e) => { setStatus(e.target.value); setPage(1) }} /></div>
        {editor ? (
          <div className="sm:w-56"><Select aria-label="Курс" value={course} placeholder="Все курсы" options={toList(courses.data).rows.map((c) => ({ value: String(c.id), label: String(c.title) }))} onChange={(e) => { setCourse(e.target.value); setPage(1) }} /></div>
        ) : null}
        <div className="sm:w-56">
          <Select aria-label="Ответственный" value={assignee} placeholder="Все ответственные" onChange={(e) => { setAssignee(e.target.value); setPage(1) }}
            options={[...(meta.data?.user_id ? [{ value: String(meta.data.user_id), label: 'Мои заявки' }] : []), ...staff.filter((u) => u.id !== meta.data?.user_id).map((u) => ({ value: String(u.id), label: u.name }))]} />
        </div>
      </div>

      {query.isPending ? <ListSkeleton rows={6} thumb={false} /> : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : rows.length ? (
        <>
          <div className="hidden overflow-x-auto rounded-2xl border border-border bg-surface lg:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-muted/60 text-left text-xs text-ink-muted">
                  <th className="px-4 py-2.5 font-medium">Родитель</th>
                  <th className="px-3 py-2.5 font-medium">Ребёнок</th>
                  <th className="px-3 py-2.5 font-medium">Курс</th>
                  <th className="px-3 py-2.5 font-medium">Дата</th>
                  <th className="px-3 py-2.5 font-medium">Источник</th>
                  <th className="px-3 py-2.5 font-medium">Ответственный</th>
                  <th className="px-4 py-2.5 font-medium">Статус</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((row) => (
                  <tr key={row.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(row.id)}>
                    <td className="px-4 py-2.5">
                      <button type="button" className="text-left font-medium text-ink hover:text-brand-600" onClick={(e) => { e.stopPropagation(); setOpen(row.id) }}>{String(row.parent_name)}</button>
                      <a href={contactHref(row)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="block text-xs font-medium text-brand-600 hover:underline">{String(row.phone)}</a>
                    </td>
                    <td className="px-3 py-2.5 text-ink-secondary">{[row.child_name, row.child_age ? `${row.child_age} лет` : ''].filter(Boolean).join(', ') || '—'}</td>
                    <td className="max-w-48 truncate px-3 py-2.5 text-ink-secondary">{String(row.course_title ?? '—')}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-ink-muted" title={formatDate(row.created_at, true)}>{relativeTime(row.created_at)}</td>
                    <td className="max-w-40 truncate px-3 py-2.5 text-xs text-ink-muted">{source(row)}</td>
                    <td className="px-3 py-2.5 text-ink-secondary">{String(row.assigned_to_name ?? '—')}</td>
                    <td className="px-4 py-2.5"><StatusChip status={String(row.status)} statuses={statuses} />{Number(row.repeat_count) ? <span className="ml-1.5 text-xs text-ink-muted">×{Number(row.repeat_count) + 1}</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-2 lg:hidden">
            {rows.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => setOpen(row.id)} className="w-full rounded-2xl border border-border bg-surface p-3.5 text-left">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">{String(row.parent_name)}</p>
                      <p className="text-sm text-brand-600">{String(row.phone)}</p>
                    </div>
                    <StatusChip status={String(row.status)} statuses={statuses} />
                  </div>
                  <p className="mt-1.5 truncate text-xs text-ink-secondary">{[row.course_title, row.child_age ? `ребёнку ${row.child_age} лет` : '', relativeTime(row.created_at)].filter(Boolean).join(' · ')}</p>
                  {row.assigned_to_name ? <p className="mt-1 text-xs text-ink-muted">Ответственный: {String(row.assigned_to_name)}</p> : null}
                </button>
              </li>
            ))}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : <EmptyState title={search || status || course || assignee ? 'Ничего не найдено' : 'Заявок пока нет'} description={search || status ? 'Измените поиск или фильтры.' : 'Новые заявки с формы «Записать ребёнка» появятся здесь.'} />}

      {openRow && meta.data ? <LeadDrawer row={openRow} meta={meta.data} onClose={() => setOpen(null)} /> : null}
    </div>
  )
}

const source = (row: Row) => [row.utm_source ? `${row.utm_source}${row.utm_campaign ? ` / ${row.utm_campaign}` : ''}` : '', row.source].filter(Boolean).join(' · ') || 'сайт'

export function LeadDrawer({ row, meta, onClose }: { row: Row; meta: SiteMeta; onClose: () => void }) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [note, setNote] = useState(String(row.note ?? ''))
  const [child, setChild] = useState(String(row.child_name ?? ''))
  const [busy, setBusy] = useState<string | null>(null)
  useEffect(() => { setNote(String(row.note ?? '')); setChild(String(row.child_name ?? '')) }, [row.id, row.note, row.child_name])
  const statuses = meta.choices.lead_status ?? []
  const staff = meta.staff ?? []
  const save = async (name: string, body: Record<string, unknown>, ok: string) => {
    setBusy(name)
    try {
      await siteCmsApi.save('leads', row.id, body)
      await invalidate()
      showToast(ok, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setBusy(null)
    }
  }
  const history = ((row.status_history as { at: string; from: string; to: string; by: string }[] | undefined) ?? []).slice().reverse()
  const method = (row.contact_method as keyof typeof METHOD_ICON) ?? 'phone'
  const Icon = METHOD_ICON[method] ?? Phone
  const label = (s: string) => statuses.find((x) => x.value === s)?.label ?? s

  return (
    <Drawer isOpen onClose={onClose} title={String(row.parent_name)} side="right" size="lg">
      <div className="space-y-5">
        <div className="flex flex-wrap gap-2">
          <a href={contactHref(row)} target="_blank" rel="noreferrer" className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600">
            <Icon className="size-4" aria-hidden />{method === 'phone' ? 'Позвонить' : method === 'whatsapp' ? 'WhatsApp' : 'Telegram'}
          </a>
          <a href={`tel:${String(row.phone)}`} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-border px-4 text-sm font-medium text-ink">
            <Phone className="size-4" aria-hidden />{String(row.phone)}
          </a>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">Статус</span>
            <Select value={String(row.status)} options={statuses} disabled={busy === 'status'} onChange={(e) => save('status', { status: e.target.value }, `Статус: ${label(e.target.value)}`)} />
          </label>
          <div>
            <span className="mb-1.5 flex items-center justify-between text-sm font-medium text-ink">
              <span id="lead-assignee">Ответственный</span>
              {meta.user_id && row.assigned_to !== meta.user_id ? (
                <button type="button" className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline" onClick={() => save('assign', { assigned_to: meta.user_id }, 'Заявка назначена на вас')}>
                  <UserCheck className="size-3.5" aria-hidden />Взять себе
                </button>
              ) : null}
            </span>
            <Select aria-labelledby="lead-assignee" value={row.assigned_to ? String(row.assigned_to) : ''} placeholder="Не назначен" options={staff.map((u) => ({ value: String(u.id), label: u.name }))}
              onChange={(e) => save('assign', { assigned_to: e.target.value ? Number(e.target.value) : null }, 'Ответственный изменён')} />
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl bg-surface-muted p-4 text-sm">
          <Item label="Интересующий курс" value={String(row.course_title ?? '—')} />
          <Item label="Возраст ребёнка" value={row.child_age ? `${row.child_age} лет` : '—'} />
          <Item label="Филиал" value={String(row.branch_name ?? '—')} />
          <Item label="Как связаться" value={meta.choices.contact_method?.find((c) => c.value === row.contact_method)?.label ?? '—'} />
          <Item label="Дата заявки" value={formatDate(row.created_at, true)} />
          <Item label="Источник" value={source(row)} />
          {Number(row.repeat_count) ? <Item label="Повторных отправок" value={String(row.repeat_count)} /> : null}
          {row.language ? <Item label="Язык сайта" value={String(row.language).toUpperCase()} /> : null}
        </dl>

        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink">Имя ребёнка</span>
          <div className="flex gap-2">
            <Input value={child} onChange={(e) => setChild(e.target.value)} placeholder="Если родитель назвал" />
            <Button variant="secondary" disabled={child === String(row.child_name ?? '')} isLoading={busy === 'child'} onClick={() => save('child', { child_name: child }, 'Сохранено')}>OK</Button>
          </div>
        </label>

        {row.message ? (
          <div>
            <p className="mb-1.5 text-sm font-medium text-ink">Сообщение с сайта</p>
            <p className="rounded-xl border border-border px-3 py-2 text-sm whitespace-pre-line text-ink">{String(row.message)}</p>
          </div>
        ) : null}

        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink">Комментарий менеджера</span>
          <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Договорились о пробном уроке в субботу…" />
          <div className="mt-2 flex justify-end">
            <Button size="sm" disabled={note === String(row.note ?? '')} isLoading={busy === 'note'} onClick={() => save('note', { note }, 'Комментарий сохранён')}>Сохранить комментарий</Button>
          </div>
        </label>

        <section>
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-ink"><Clock className="size-4 text-ink-muted" aria-hidden />История статусов</h3>
          <ol className="relative space-y-3 border-l border-border pl-4">
            {history.map((h, i) => (
              <li key={i} className="text-sm">
                <span className={cn('absolute -left-[5px] mt-1.5 size-2.5 rounded-full ring-2 ring-surface', LEAD_TONE[h.to]?.dot ?? 'bg-ink-muted')} aria-hidden />
                <p className="text-ink"><span className="text-ink-muted">{label(h.from)} →</span> <span className="font-medium">{label(h.to)}</span></p>
                <p className="text-xs text-ink-muted">{formatDate(h.at, true)}{h.by ? ` · ${h.by}` : ''}</p>
              </li>
            ))}
            <li className="text-sm">
              <span className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full bg-cms-gold ring-2 ring-surface" aria-hidden />
              <p className="font-medium text-ink">Заявка получена</p>
              <p className="text-xs text-ink-muted">{formatDate(row.created_at, true)}</p>
            </li>
          </ol>
        </section>
      </div>
    </Drawer>
  )
}

function Item({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-xs text-ink-muted">{label}</dt><dd className="truncate font-medium text-ink">{value}</dd></div>
}

function RegistrationInbox() {
  const meta = useSiteMeta()
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const query = useSiteList('registrations', { search: search || undefined, status: status || undefined, page, page_size: PAGE_SIZE, ordering: '-created_at' })
  const { rows, count } = toList(query.data)
  const statuses = meta.data?.choices.registration_status ?? []
  const setRowStatus = async (row: Row, value: string) => {
    try {
      await siteCmsApi.save('registrations', row.id, { status: value })
      await invalidate()
      showToast('Статус изменён', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="sm:w-72"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Имя или телефон" /></div>
        <div className="sm:w-52"><Select aria-label="Статус" value={status} placeholder="Все статусы" options={statuses} onChange={(e) => { setStatus(e.target.value); setPage(1) }} /></div>
      </div>
      {query.isPending ? <ListSkeleton rows={5} thumb={false} /> : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : rows.length ? (
        <>
          <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-surface">
            {rows.map((row) => (
              <li key={row.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink">{String(row.parent_name)} <a href={`tel:${String(row.phone)}`} className="ml-1 text-sm font-medium text-brand-600 hover:underline">{String(row.phone)}</a></p>
                  <p className="truncate text-xs text-ink-secondary">{[row.event_title, row.child_name, row.child_age ? `${row.child_age} лет` : '', relativeTime(row.created_at)].filter(Boolean).join(' · ')}</p>
                  {row.comment ? <p className="mt-1 text-sm whitespace-pre-line text-ink">{String(row.comment)}</p> : null}
                </div>
                <div className="sm:w-44"><Select aria-label={`Статус: ${String(row.parent_name)}`} value={String(row.status)} options={statuses} onChange={(e) => setRowStatus(row, e.target.value)} /></div>
              </li>
            ))}
          </ul>
          {count > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} totalCount={count} onPageChange={setPage} /> : null}
        </>
      ) : <EmptyState title="Регистраций нет" description="Регистрации на события с открытой записью появятся здесь." />}
    </div>
  )
}

/** /marketing/site/leads/board — доска статусов: перетаскивание карточек между колонками. */
export function LeadsBoardPage() {
  const meta = useSiteMeta()
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [drag, setDrag] = useState<number | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const query = useSiteList('leads', { search: search || undefined, page_size: 200, ordering: '-created_at' })
  const { rows } = toList(query.data)
  const statuses = meta.data?.choices.lead_status ?? []
  const move = async (id: number, status: string) => {
    const row = rows.find((r) => r.id === id)
    if (!row || row.status === status) return
    try {
      await siteCmsApi.save('leads', id, { status })
      await invalidate()
      showToast(`«${String(row.parent_name)}» → ${statuses.find((s) => s.value === status)?.label}`, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }
  const openRow = rows.find((r) => r.id === open) ?? null
  return (
    <CmsPage title="Статусы заявок" description="Перетащите карточку в другую колонку или откройте её, чтобы сменить статус и назначить ответственного. Показаны последние 200 заявок."
      actions={<Link to={`${CMS_BASE}/leads`} className="inline-flex h-10 items-center gap-2 rounded-lg border border-brand-200 bg-surface px-4 text-sm font-medium text-brand-700 hover:bg-brand-50"><List className="size-4" aria-hidden />Список</Link>}>
      <div className="sm:w-72"><SearchInput value={search} onChange={setSearch} placeholder="Имя или телефон" /></div>
      {query.isPending ? (
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-72 rounded-2xl" />)}</div>
      ) : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} /> : (
        <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0 xl:grid xl:grid-cols-6 xl:overflow-visible">
          {statuses.map((s) => {
            const items = rows.filter((r) => r.status === s.value)
            return (
              <section key={s.value} aria-label={s.label}
                onDragOver={(e) => { e.preventDefault(); setOver(s.value) }} onDragLeave={() => setOver(null)}
                onDrop={() => { if (drag !== null) move(drag, s.value); setDrag(null); setOver(null) }}
                className={cn('flex w-[78vw] max-w-xs shrink-0 snap-start flex-col rounded-2xl border bg-surface-muted/70 sm:w-72 xl:w-auto xl:max-w-none', over === s.value ? 'border-brand-500 bg-brand-50' : 'border-border')}>
                <h2 className="flex items-center gap-2 px-3 py-2.5 text-sm font-semibold text-ink">
                  <span className={cn('size-2 rounded-full', LEAD_TONE[s.value]?.dot)} aria-hidden />{s.label}
                  <span className="ml-auto rounded-full bg-surface px-2 py-0.5 text-xs text-ink-secondary">{items.length}</span>
                </h2>
                <ul className="flex max-h-[65vh] flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
                  {items.map((row) => (
                    <li key={row.id} draggable onDragStart={() => setDrag(row.id)} onDragEnd={() => setDrag(null)}
                      className={cn('rounded-xl border border-border bg-surface p-3 shadow-sm', drag === row.id && 'opacity-50')}>
                      <button type="button" onClick={() => setOpen(row.id)} className="w-full text-left">
                        <p className="truncate text-sm font-medium text-ink">{String(row.parent_name)}</p>
                        <p className="text-xs text-brand-600">{String(row.phone)}</p>
                        <p className="mt-1 truncate text-xs text-ink-muted">{[row.course_title, relativeTime(row.created_at)].filter(Boolean).join(' · ')}</p>
                        {row.assigned_to_name ? <p className="mt-1 truncate text-xs text-ink-secondary">Ответственный: {String(row.assigned_to_name)}</p> : null}
                      </button>
                      <Select aria-label={`Статус: ${String(row.parent_name)}`} value={String(row.status)} options={statuses} className="mt-2 h-8 text-xs xl:hidden"
                        onChange={(e) => move(row.id, e.target.value)} />
                    </li>
                  ))}
                  {!items.length ? <li className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-ink-muted">Пусто</li> : null}
                </ul>
              </section>
            )
          })}
        </div>
      )}
      {openRow && meta.data ? <LeadDrawer row={openRow} meta={meta.data} onClose={() => setOpen(null)} /> : null}
    </CmsPage>
  )
}
