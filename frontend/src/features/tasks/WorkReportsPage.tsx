import { useState } from 'react'
import { Plus } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/hooks/useAuth'
import { useWorkReportMutations, useWorkReports, useWorkReportsMeta } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'
import type { ReportKind, WorkReport } from '@/types/operations'

import { LevelBadge, Note, QueryView, Section, Table, dateTime, shortDate } from '../operations/shared'

function ReportModal({ report, onClose }: { report: Partial<WorkReport> & { kind: ReportKind }; onClose: () => void }) {
  const meta = useWorkReportsMeta()
  const { save, submit } = useWorkReportMutations()
  const { showToast } = useToast()
  const [form, setForm] = useState({ kind: report.kind, period_start: report.period_start ?? new Date().toISOString().slice(0, 10), done: report.done ?? '', plans: report.plans ?? '', problems: report.problems ?? '', metrics: report.metrics ?? {} })
  const onError = (e: unknown) => showToast(extractErrorMessage(e), 'error')
  const persist = (andSubmit: boolean) => save.mutate({ id: report.id ?? null, body: form }, {
    onError,
    onSuccess: (saved) => {
      if (!andSubmit) { showToast('Черновик сохранён', 'success'); onClose(); return }
      submit.mutate(saved.id, { onError, onSuccess: () => { showToast('Отчёт сдан', 'success'); onClose() } })
    },
  })
  return (
    <Modal isOpen onClose={onClose} title={report.id ? 'Отчёт' : 'Новый отчёт'} size="lg">
      <div className="space-y-3">
        {report.review_comment ? <Note>Комментарий руководителя: {report.review_comment}</Note> : null}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><span className="field-label">Вид</span><Select disabled={Boolean(report.id)} value={form.kind} options={meta.data?.kinds ?? []} onChange={(e) => setForm({ ...form, kind: e.target.value as ReportKind })} /></label>
          <label className="block"><span className="field-label">За дату (неделя / месяц — любой её день)</span><Input type="date" value={form.period_start} onChange={(e) => setForm({ ...form, period_start: e.target.value })} /></label>
        </div>
        {meta.data?.metrics.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {meta.data.metrics.map((f) => f.type === 'bool' ? (
              <label key={f.key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.metrics[f.key])} onChange={(e) => setForm({ ...form, metrics: { ...form.metrics, [f.key]: e.target.checked } })} />{f.label}</label>
            ) : (
              <label key={f.key} className="block"><span className="field-label">{f.label}</span><Input type="number" min={0} step={f.type === 'money' ? '0.01' : '1'} value={form.metrics[f.key] === undefined ? '' : String(form.metrics[f.key])}
                onChange={(e) => { const next = { ...form.metrics }; if (e.target.value === '') delete next[f.key]; else next[f.key] = Number(e.target.value); setForm({ ...form, metrics: next }) }} /></label>
            ))}
          </div>
        ) : null}
        <label className="block"><span className="field-label">Что сделано</span><Textarea rows={4} value={form.done} onChange={(e) => setForm({ ...form, done: e.target.value })} /></label>
        <label className="block"><span className="field-label">Планы</span><Textarea rows={2} value={form.plans} onChange={(e) => setForm({ ...form, plans: e.target.value })} /></label>
        <label className="block"><span className="field-label">Проблемы</span><Textarea rows={2} value={form.problems} onChange={(e) => setForm({ ...form, problems: e.target.value })} /></label>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Отмена</Button><Button variant="secondary" isLoading={save.isPending && !submit.isPending} onClick={() => persist(false)}>Черновик</Button><Button isLoading={submit.isPending} onClick={() => persist(true)}>Сдать отчёт</Button></div>
      </div>
    </Modal>
  )
}

function ReviewModal({ report, onClose }: { report: WorkReport; onClose: () => void }) {
  const { review } = useWorkReportMutations()
  const { showToast } = useToast()
  const [comment, setComment] = useState('')
  const decide = (decision: 'accept' | 'return') => review.mutate({ id: report.id, decision, comment }, { onError: (e) => showToast(extractErrorMessage(e), 'error'), onSuccess: () => { showToast(decision === 'accept' ? 'Отчёт принят' : 'Отчёт возвращён', 'success'); onClose() } })
  return (
    <Modal isOpen onClose={onClose} title={`${report.kind_label} отчёт: ${report.author.full_name}`} size="lg">
      <div className="space-y-3 text-sm">
        <p className="text-ink-secondary">За {shortDate(report.period_start)}{report.period_end !== report.period_start ? ` — ${shortDate(report.period_end)}` : ''}, сдан {dateTime(report.submitted_at)}</p>
        {Object.keys(report.metrics).length ? <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">{Object.entries(report.metrics).map(([k, v]) => <div key={k} className="rounded-lg bg-surface-muted px-3 py-2"><dt className="field-label">{k}</dt><dd className="font-semibold">{typeof v === 'boolean' ? (v ? 'Да' : 'Нет') : v}</dd></div>)}</dl> : null}
        <div><p className="field-label">Что сделано</p><p className="whitespace-pre-line">{report.done || '—'}</p></div>
        <div><p className="field-label">Планы</p><p className="whitespace-pre-line">{report.plans || '—'}</p></div>
        <div><p className="field-label">Проблемы</p><p className="whitespace-pre-line">{report.problems || '—'}</p></div>
        {report.status === 'submitted' ? (
          <>
            <Textarea rows={2} value={comment} placeholder="Комментарий (обязателен при возврате)" onChange={(e) => setComment(e.target.value)} />
            <div className="flex justify-end gap-2"><Button variant="danger" disabled={!comment.trim()} onClick={() => decide('return')}>Вернуть</Button><Button isLoading={review.isPending} onClick={() => decide('accept')}>Принять</Button></div>
          </>
        ) : null}
      </div>
    </Modal>
  )
}

/** /work-reports — свои ежедневные, еженедельные и месячные отчёты (и
 * отчёты отдела на проверку — у руководителя отдела). */
export function WorkReportsPage() {
  const { user } = useAuth()
  const meta = useWorkReportsMeta()
  const [tab, setTab] = useState<'mine' | 'team'>('mine')
  const [kind, setKind] = useState<ReportKind | ''>('')
  const list = useWorkReports({ mine: tab === 'mine' ? '1' : undefined, kind: kind || undefined, status: tab === 'team' ? 'submitted' : undefined, page_size: 50 })
  const [editing, setEditing] = useState<(Partial<WorkReport> & { kind: ReportKind }) | null>(null)
  const [reviewing, setReviewing] = useState<WorkReport | null>(null)
  const missing = (meta.data?.obligations ?? []).filter((o) => o.status === 'missing')
  const isLead = ['team_lead', 'rop', 'dop', 'operations_director', 'director', 'admin'].includes(user?.role ?? '')
  return (
    <div className="space-y-4">
      <PageHeader title="Мои отчёты" description="Ежедневные, еженедельные и месячные отчёты о работе" actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing({ kind: 'daily' })}>Отчёт</Button>} />
      {user?.role === 'team_lead' ? <Note>Отчёты Team Lead ведутся в «Рабочем журнале» — здесь можно проверять отчёты команды.</Note> : null}
      {missing.length ? (
        <Section title="Не сдано">
          <ul className="space-y-1 text-sm">{missing.map((o) => <li key={`${o.kind}-${o.period_start}`} className="flex items-center justify-between"><span>{o.kind === 'daily' ? 'Ежедневный' : o.kind === 'weekly' ? 'Еженедельный' : 'Ежемесячный'} за {shortDate(o.period_start)} (срок {dateTime(o.due)})</span><Button size="sm" variant="secondary" onClick={() => setEditing({ kind: o.kind, period_start: o.period_start })}>Заполнить</Button></li>)}</ul>
        </Section>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {isLead ? <SegmentedControl aria-label="Чьи отчёты" value={tab} onChange={setTab} options={[{ value: 'mine', label: 'Мои' }, { value: 'team', label: 'На проверку' }]} /> : null}
        <div className="w-48"><Select aria-label="Вид" placeholder="Все виды" value={kind} options={meta.data?.kinds ?? []} onChange={(e) => setKind(e.target.value as ReportKind | '')} /></div>
      </div>
      <QueryView query={list}>
        {(data) => (
          <Section title={tab === 'mine' ? 'Мои отчёты' : 'Ждут проверки'} padding={false}>
            <Table empty={!data.results.length} headers={['Отчёт', 'Период', ...(tab === 'team' ? ['Сотрудник'] : []), 'Статус', 'Сдан', '']}>
              {data.results.map((r) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.kind_label}</td>
                  <td>{shortDate(r.period_start)}{r.period_end !== r.period_start ? ` — ${shortDate(r.period_end)}` : ''}</td>
                  {tab === 'team' ? <td>{r.author.full_name}</td> : null}
                  <td><LevelBadge level={r.status} label={r.status_label} /></td>
                  <td className="text-sm">{dateTime(r.submitted_at)}</td>
                  <td className="text-right">{tab === 'team' || r.author.id !== user?.id ? <Button size="sm" variant="secondary" onClick={() => setReviewing(r)}>Открыть</Button> : ['draft', 'returned'].includes(r.status) ? <Button size="sm" variant="secondary" onClick={() => setEditing(r)}>Редактировать</Button> : <Button size="sm" variant="ghost" onClick={() => setReviewing(r)}>Просмотр</Button>}</td>
                </tr>
              ))}
            </Table>
          </Section>
        )}
      </QueryView>
      {editing ? <ReportModal report={editing} onClose={() => setEditing(null)} /> : null}
      {reviewing ? <ReviewModal report={reviewing} onClose={() => setReviewing(null)} /> : null}
    </div>
  )
}
