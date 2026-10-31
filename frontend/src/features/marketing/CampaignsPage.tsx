import { useState } from 'react'
import { Plus, Target } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useCampaigns, useDeleteCampaign, useMarketingMeta, useSaveCampaign } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { Campaign, CampaignInput } from '@/types/marketing'
import { formatDateShort } from '@/utils/format'

const money = (value: string | null | undefined) => (value === null || value === undefined ? '—' : `${Number(value).toLocaleString('ru-RU')} сом`)

function CampaignDialog({ campaign, onClose }: { campaign: Campaign | null; onClose: () => void }) {
  const meta = useMarketingMeta()
  const save = useSaveCampaign()
  const remove = useDeleteCampaign()
  const { showToast } = useToast()
  const [form, setForm] = useState<CampaignInput>({
    name: campaign?.name ?? '', channel: campaign?.channel ?? 'instagram', responsible: campaign?.responsible ?? meta.data?.me ?? null,
    status: campaign?.status ?? 'planned', start_date: campaign?.start_date ?? meta.data?.today ?? '', end_date: campaign?.end_date ?? null,
    budget: campaign?.budget ?? '0', spent: campaign?.spent ?? '0', leads: campaign?.leads ?? 0, sales: campaign?.sales ?? 0, result: campaign?.result ?? '',
  })
  const budget = meta.data?.can_view_budget !== false
  const onError = (e: unknown) => showToast(extractErrorMessage(e), 'error')
  const submit = () => {
    const body = { ...form }
    if (!budget) { delete body.budget; delete body.spent }
    save.mutate({ id: campaign?.id ?? null, body }, { onError, onSuccess: () => { showToast('Кампания сохранена', 'success'); onClose() } })
  }
  return (
    <Modal isOpen onClose={onClose} title={campaign ? 'Кампания' : 'Новая кампания'} size="lg" icon={<Target className="size-5" aria-hidden />}>
      <div className="space-y-3">
        <label className="block"><span className="field-label">Название</span><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><span className="field-label">Канал</span><Select value={form.channel} options={meta.data?.channels ?? []} onChange={(e) => setForm({ ...form, channel: e.target.value as Campaign['channel'] })} /></label>
          <label className="block"><span className="field-label">Ответственный</span><Select value={form.responsible ? String(form.responsible) : ''} placeholder="Не назначен" options={(meta.data?.team ?? []).map((m) => ({ value: String(m.id), label: m.full_name }))} onChange={(e) => setForm({ ...form, responsible: e.target.value ? Number(e.target.value) : null })} /></label>
          <label className="block"><span className="field-label">Статус</span><Select value={form.status} options={meta.data?.campaign_statuses ?? []} onChange={(e) => setForm({ ...form, status: e.target.value as Campaign['status'] })} /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block"><span className="field-label">Запуск</span><Input type="date" value={form.start_date ?? ''} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></label>
            <label className="block"><span className="field-label">Окончание</span><Input type="date" value={form.end_date ?? ''} onChange={(e) => setForm({ ...form, end_date: e.target.value || null })} /></label>
          </div>
          {budget ? <>
            <label className="block"><span className="field-label">Бюджет, сом</span><Input type="number" min={0} step="0.01" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} /></label>
            <label className="block"><span className="field-label">Израсходовано, сом</span><Input type="number" min={0} step="0.01" value={form.spent} onChange={(e) => setForm({ ...form, spent: e.target.value })} /></label>
          </> : null}
          <label className="block"><span className="field-label">Лидов</span><Input type="number" min={0} value={form.leads} onChange={(e) => setForm({ ...form, leads: Number(e.target.value) })} /></label>
          <label className="block"><span className="field-label">Продаж</span><Input type="number" min={0} value={form.sales} onChange={(e) => setForm({ ...form, sales: Number(e.target.value) })} /></label>
        </div>
        <label className="block"><span className="field-label">Результат</span><Textarea rows={3} value={form.result} onChange={(e) => setForm({ ...form, result: e.target.value })} /></label>
        <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row">
          {campaign?.can_delete ? <Button variant="ghost" className="text-danger sm:mr-auto" onClick={() => remove.mutate(campaign.id, { onError, onSuccess: onClose })}>Удалить</Button> : <span className="sm:flex-1" />}
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button isLoading={save.isPending} disabled={!form.name?.trim() || !form.start_date} onClick={submit}>Сохранить</Button>
        </div>
      </div>
    </Modal>
  )
}

/** /marketing/campaigns — рекламные кампании: бюджет, расход, лиды, CPL и
 * результат. CRM в LMS нет, поэтому лиды и продажи вносит маркетинг. */
export function MarketingCampaignsPage() {
  const meta = useMarketingMeta()
  const [status, setStatus] = useState('')
  const query = useCampaigns({ status: status || undefined, page_size: 100 })
  const [open, setOpen] = useState<Campaign | null | undefined>(undefined)
  const budget = meta.data?.can_view_budget !== false
  return (
    <div className="space-y-4">
      <PageHeader title="Кампании" description="Рекламные кампании, лиды, стоимость лида и результат"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setOpen(null)}>Новая кампания</Button>} />
      <div className="md:w-56"><Select aria-label="Статус" placeholder="Все статусы" value={status} options={meta.data?.campaign_statuses ?? []} onChange={(e) => setStatus(e.target.value)} /></div>
      {query.isPending ? <LoadingState /> : query.isError ? <ErrorState message={extractErrorMessage(query.error)} onRetry={() => void query.refetch()} /> : query.data.results.length === 0 ? (
        <EmptyState title="Кампаний пока нет" description="Добавьте кампанию — лиды и CPL появятся в отчётах и у операционного директора." />
      ) : (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Кампания</th><th>Канал</th><th>Период</th><th>Статус</th>{budget ? <><th>Бюджет</th><th>Расход</th></> : null}<th>Лиды</th>{budget ? <th>CPL</th> : null}<th>Продажи</th><th>Конверсия</th></tr></thead>
            <tbody>
              {query.data.results.map((c) => (
                <tr key={c.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(c)}>
                  <td className="font-medium">{c.name}<span className="block text-xs text-ink-secondary">{c.responsible_info?.full_name ?? '—'}</span></td>
                  <td>{c.channel_label}</td>
                  <td className="whitespace-nowrap">{formatDateShort(c.start_date)}{c.end_date ? ` — ${formatDateShort(c.end_date)}` : ''}</td>
                  <td><Badge tone={c.status === 'active' ? 'success' : c.status === 'cancelled' ? 'danger' : 'muted'}>{c.status_label}</Badge></td>
                  {budget ? <><td>{money(c.budget)}</td><td>{money(c.spent)}</td></> : null}
                  <td className="tabular-nums">{c.leads}</td>
                  {budget ? <td>{money(c.cost_per_lead)}</td> : null}
                  <td className="tabular-nums">{c.sales}</td>
                  <td>{c.conversion === null ? '—' : `${c.conversion}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open !== undefined ? <CampaignDialog campaign={open} onClose={() => setOpen(undefined)} /> : null}
    </div>
  )
}
