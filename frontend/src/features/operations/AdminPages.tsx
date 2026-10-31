import { useEffect, useState } from 'react'
import { Download, Plus, Printer, RefreshCw } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { operationsApi } from '@/api/operations'
import { useIssueActions, useOpsIssue, useOpsIssues, useOpsMeta, useOpsReports, useOpsSettings, useSaveOpsSettings } from '@/hooks/useOperations'
import { extractErrorMessage } from '@/lib/apiError'
import type { OpsSettings, Priority, ReportKind } from '@/types/operations'

import { LevelBadge, Note, OpsFilters, PriorityBadge, QueryView, Section, Table, dateTime, saveBlob, shortDate, useOpsFilters } from './shared'

/** /operations/reports — 8 видов отчётов: просмотр, фильтры, CSV, Excel,
 * печать, история выгрузок и сданные отчёты сотрудников. */
export function OperationsReportsPage() {
  const filters = useOpsFilters('this_month')
  const kind = filters.raw.get('kind') ?? 'monthly'
  const query = useOpsReports({ ...filters.params, kind })
  const { showToast } = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const download = async (format: 'csv' | 'xlsx') => {
    setBusy(format)
    try {
      const { blob, name } = await operationsApi.exportReport({ ...filters.params, kind, export_format: format })
      saveBlob(blob, name)
      void query.refetch()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="space-y-4">
      <PageHeader title="Отчёты" description="Операционные, KPI-отчёты, посещаемость и задачи — с выгрузкой и печатью"
        actions={
          <div className="flex flex-wrap gap-2 print:hidden">
            <Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={busy === 'csv'} onClick={() => void download('csv')}>CSV</Button>
            <Button variant="secondary" leftIcon={<Download className="size-4" aria-hidden />} isLoading={busy === 'xlsx'} onClick={() => void download('xlsx')}>Excel</Button>
            <Button variant="secondary" leftIcon={<Printer className="size-4" aria-hidden />} onClick={() => window.print()}>Печать</Button>
          </div>
        } />
      <OpsFilters filters={filters} show={['department', 'employee']}>
        <div className="col-span-2 md:w-60">
          <Select aria-label="Вид отчёта" value={kind} options={query.data?.kinds ?? [{ value: kind, label: 'Отчёт' }]} onChange={(e) => filters.set({ kind: e.target.value })} />
        </div>
      </OpsFilters>
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <p className="text-sm text-ink-secondary">{data.kinds.find((k) => k.value === data.kind)?.label} · {data.filters.label} ({shortDate(data.filters.start)} — {shortDate(data.filters.end)})</p>
            {data.sheets.map((sheet) => (
              <Section key={sheet.title} title={`${sheet.title} (${sheet.total})`} padding={false}>
                <Table empty={!sheet.rows.length} headers={sheet.headers}>
                  {sheet.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} className="text-sm">{cell === '' ? '—' : cell}</td>)}</tr>)}
                </Table>
                {sheet.total > sheet.rows.length ? <p className="px-4 py-2 text-xs text-ink-muted">Показаны первые {sheet.rows.length} строк — полностью в выгрузке.</p> : null}
              </Section>
            ))}
            <div className="grid gap-4 lg:grid-cols-2 print:hidden">
              <Section title="Отчёты сотрудников за период" padding={false}>
                <Table empty={!data.employee_reports.length} headers={['Сотрудник', 'Отчёт', 'Период', 'Статус']}>
                  {data.employee_reports.map((r) => <tr key={r.id}><td><Link className="hover:text-brand-700" to={`/operations/employees/${r.author.id}`}>{r.author.full_name}</Link></td><td>{r.kind_label}</td><td>{shortDate(r.period_start)}</td><td><LevelBadge level={r.status} label={r.status_label} /></td></tr>)}
                </Table>
              </Section>
              <Section title="История выгрузок" padding={false}>
                <Table empty={!data.history.length} headers={['Когда', 'Вид', 'Формат', 'Строк', 'Кто']}>
                  {data.history.map((h) => <tr key={h.id}><td className="text-sm">{dateTime(h.created_at)}</td><td>{data.kinds.find((k) => k.value === h.kind)?.label ?? h.kind}</td><td className="uppercase">{h.format}</td><td>{h.rows}</td><td className="text-sm">{h.created_by?.full_name ?? '—'}</td></tr>)}
                </Table>
              </Section>
            </div>
          </div>
        )}
      </QueryView>
    </div>
  )
}

function IssueDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const query = useOpsIssue(id)
  const meta = useOpsMeta()
  const actions = useIssueActions()
  const { showToast } = useToast()
  const [comment, setComment] = useState('')
  const onError = (e: unknown) => showToast(extractErrorMessage(e), 'error')
  return (
    <Drawer isOpen onClose={onClose} title="Проблема" side="right" size="lg">
      <QueryView query={query}>
        {(issue) => (
          <div className="space-y-4">
            <div>
              <div className="mb-1 flex flex-wrap gap-1.5"><LevelBadge level={issue.status} label={issue.status_label} /><PriorityBadge priority={issue.priority} label={issue.priority_label} />{issue.reopen_count ? <LevelBadge level="low" label={`Повторно: ${issue.reopen_count}`} /> : null}</div>
              <h3 className="text-lg font-semibold">{issue.title}</h3>
              <p className="mt-1 whitespace-pre-line text-sm text-ink-secondary">{issue.description || '—'}</p>
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="field-label">Тип</dt><dd>{issue.kind_label}</dd></div>
              <div><dt className="field-label">Отдел</dt><dd>{issue.department_label}</dd></div>
              <div><dt className="field-label">Обнаружена</dt><dd>{dateTime(issue.detected_at)}</dd></div>
              <div><dt className="field-label">Последняя проверка</dt><dd>{dateTime(issue.last_seen_at)} (дней: {issue.times_detected})</dd></div>
            </dl>
            {issue.link ? <Link to={issue.link} className="text-sm font-medium text-brand-700 hover:underline">Перейти к объекту</Link> : null}
            <label className="block"><span className="field-label">Ответственный</span>
              <Select value={issue.responsible ? String(issue.responsible.id) : ''} placeholder="Не назначен" options={(meta.data?.employees ?? []).map((e) => ({ value: String(e.id), label: `${e.full_name} — ${e.role_label}` }))}
                onChange={(e) => actions.assign.mutate({ id, responsible: e.target.value ? Number(e.target.value) : null }, { onError })} /></label>
            <div className="space-y-2">
              <Textarea rows={2} placeholder="Комментарий (обязателен при отклонении)" value={comment} onChange={(e) => setComment(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                {issue.status === 'open' ? <Button size="sm" variant="secondary" onClick={() => actions.status.mutate({ id, status: 'in_progress', comment }, { onError, onSuccess: () => setComment('') })}>В работу</Button> : null}
                {['open', 'in_progress'].includes(issue.status) ? <Button size="sm" onClick={() => actions.status.mutate({ id, status: 'resolved', comment }, { onError, onSuccess: () => setComment('') })}>Решена</Button> : null}
                {['open', 'in_progress'].includes(issue.status) ? <Button size="sm" variant="ghost" onClick={() => actions.status.mutate({ id, status: 'dismissed', comment }, { onError, onSuccess: () => setComment('') })}>Отклонить</Button> : null}
                {['resolved', 'dismissed'].includes(issue.status) ? <Button size="sm" variant="secondary" onClick={() => actions.status.mutate({ id, status: 'open', comment }, { onError })}>Открыть снова</Button> : null}
                <Button size="sm" variant="ghost" disabled={!comment.trim()} onClick={() => actions.comment.mutate({ id, text: comment }, { onError, onSuccess: () => setComment('') })}>Комментарий</Button>
              </div>
            </div>
            <div>
              <h4 className="section-title mb-2">История действий</h4>
              <ol className="space-y-2 border-l border-border pl-4">
                {issue.events.map((e) => <li key={e.id} className="text-sm"><span className="font-medium">{e.action_label}</span>{e.to_status ? ` → ${e.to_status}` : ''}<span className="block text-xs text-ink-muted">{dateTime(e.created_at)} · {e.actor?.full_name ?? 'Система'}</span>{e.comment ? <span className="block text-ink-secondary">{e.comment}</span> : null}</li>)}
              </ol>
            </div>
          </div>
        )}
      </QueryView>
    </Drawer>
  )
}

function NewIssueModal({ onClose }: { onClose: () => void }) {
  const meta = useOpsMeta()
  const { create } = useIssueActions()
  const { showToast } = useToast()
  const [form, setForm] = useState({ title: '', description: '', department: 'academy', priority: 'medium' as Priority, responsible: '' })
  return (
    <Modal isOpen onClose={onClose} title="Новая проблема">
      <div className="space-y-3">
        <label className="block"><span className="field-label">Название</span><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="block"><span className="field-label">Описание</span><Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block"><span className="field-label">Отдел</span><Select value={form.department} options={meta.data?.departments ?? []} onChange={(e) => setForm({ ...form, department: e.target.value })} /></label>
          <label className="block"><span className="field-label">Приоритет</span><Select value={form.priority} options={meta.data?.priorities ?? []} onChange={(e) => setForm({ ...form, priority: e.target.value as Priority })} /></label>
        </div>
        <label className="block"><span className="field-label">Ответственный</span><Select value={form.responsible} placeholder="Не назначен" options={(meta.data?.employees ?? []).map((e) => ({ value: String(e.id), label: e.full_name }))} onChange={(e) => setForm({ ...form, responsible: e.target.value })} /></label>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button disabled={!form.title.trim()} isLoading={create.isPending} onClick={() => create.mutate({ ...form, responsible: form.responsible ? Number(form.responsible) : null }, { onSuccess: () => { showToast('Проблема добавлена', 'success'); onClose() }, onError: (e) => showToast(extractErrorMessage(e), 'error') })}>Добавить</Button></div>
      </div>
    </Modal>
  )
}

/** /operations/issues — Attention Required: автоматически найденные и
 * добавленные вручную проблемы, ответственные, статусы и история. */
export function OperationsIssuesPage() {
  const [search, setSearch] = useSearchParams()
  const meta = useOpsMeta()
  const { scan } = useIssueActions()
  const { showToast } = useToast()
  const [creating, setCreating] = useState(false)
  const get = (key: string) => search.get(key) ?? ''
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(search)
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    if (!('page' in patch)) next.delete('page')
    setSearch(next, { replace: true })
  }
  const query = useOpsIssues({ status: get('status') || 'active', kind: get('kind') || undefined, department: get('department') || undefined, priority: get('priority') || undefined, repeated: get('repeated') === '1' ? '1' : undefined, q: get('q') || undefined, page: Number(get('page') || 1) })
  const openId = get('open') ? Number(get('open')) : null
  return (
    <div className="space-y-4">
      <PageHeader title="Проблемы" description="Просрочки, несданные отчёты, незаполненные журналы, низкий KPI, пропуски студентов и повторные нарушения"
        actions={<div className="flex gap-2"><Button variant="secondary" leftIcon={<RefreshCw className="size-4" aria-hidden />} isLoading={scan.isPending} onClick={() => scan.mutate(undefined, { onSuccess: () => showToast('Проверка выполнена', 'success'), onError: (e) => showToast(extractErrorMessage(e), 'error') })}>Проверить сейчас</Button><Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>Добавить</Button></div>} />
      <div className="grid grid-cols-2 gap-2 md:flex md:flex-wrap">
        <div className="col-span-2 md:w-60"><SearchInput value={get('q')} onChange={(v) => set({ q: v })} placeholder="Поиск" /></div>
        <div className="md:w-40"><Select aria-label="Статус" value={get('status') || 'active'} options={[{ value: 'active', label: 'Активные' }, ...(meta.data?.issue_statuses ?? [])]} onChange={(e) => set({ status: e.target.value })} /></div>
        <div className="md:w-56"><Select aria-label="Тип" placeholder="Все типы" value={get('kind')} options={meta.data?.issue_kinds ?? []} onChange={(e) => set({ kind: e.target.value })} /></div>
        <div className="md:w-44"><Select aria-label="Отдел" placeholder="Все отделы" value={get('department')} options={meta.data?.departments ?? []} onChange={(e) => set({ department: e.target.value })} /></div>
        <div className="md:w-40"><Select aria-label="Приоритет" placeholder="Любой приоритет" value={get('priority')} options={meta.data?.priorities ?? []} onChange={(e) => set({ priority: e.target.value })} /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={get('repeated') === '1'} onChange={(e) => set({ repeated: e.target.checked ? '1' : '' })} />Повторные</label>
      </div>
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3"><StatCard label="Активных" value={data.summary.active} /><StatCard label="Высокий приоритет" value={data.summary.high} tone={data.summary.high ? 'danger' : 'default'} /><StatCard label="Повторные нарушения" value={data.summary.repeated} tone={data.summary.repeated ? 'warning' : 'default'} /></div>
            <Section title="Список" padding={false}>
              <Table empty={!data.results.length} headers={['Проблема', 'Тип', 'Отдел', 'Ответственный', 'Обнаружена', 'Приоритет', 'Статус']}>
                {data.results.map((i) => (
                  <tr key={i.id} className="cursor-pointer hover:bg-surface-hover" onClick={() => set({ open: String(i.id) })}>
                    <td className="font-medium">{i.title}{i.reopen_count ? <span className="ml-1 text-xs text-danger">×{i.reopen_count + 1}</span> : null}</td>
                    <td className="text-sm">{i.kind_label}</td>
                    <td className="text-sm">{i.department_label}</td>
                    <td className="text-sm">{i.responsible?.full_name ?? '—'}</td>
                    <td className="whitespace-nowrap text-sm">{dateTime(i.detected_at)}</td>
                    <td><PriorityBadge priority={i.priority} label={i.priority_label} /></td>
                    <td><LevelBadge level={i.status} label={i.status_label} /></td>
                  </tr>
                ))}
              </Table>
            </Section>
            <Pagination page={Number(get('page') || 1)} pageSize={25} totalCount={data.count} onPageChange={(page) => set({ page: String(page) })} />
          </div>
        )}
      </QueryView>
      {openId ? <IssueDrawer id={openId} onClose={() => set({ open: '' })} /> : null}
      {creating ? <NewIssueModal onClose={() => setCreating(false)} /> : null}
    </div>
  )
}

/** /operations/settings — правила модуля: обязательные отчёты по ролям,
 * сроки, напоминания, пороги, доступ к бюджетам маркетинга. */
export function OperationsSettingsPage() {
  const query = useOpsSettings()
  const save = useSaveOpsSettings()
  const { showToast } = useToast()
  const [form, setForm] = useState<OpsSettings | null>(null)
  useEffect(() => { if (query.data) setForm(query.data) }, [query.data])
  const toggle = (role: string, kind: ReportKind) => {
    if (!form) return
    const current = form.required_reports[role] ?? []
    const next = current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]
    setForm({ ...form, required_reports: { ...form.required_reports, [role]: next } })
  }
  return (
    <div className="space-y-4">
      <PageHeader title="Настройки" description="Правила, которые решает руководство: в систему не зашито ни одного норматива" />
      <QueryView query={query}>
        {() => form ? (
          <div className="space-y-4">
            <Section title="Обязательные отчёты" padding={false}>
              <Table headers={['Должность', ...(form.report_kinds ?? []).map((k) => k.label)]}>
                {(form.roles ?? []).map((role) => (
                  <tr key={role.value}>
                    <td>{role.label}</td>
                    {(form.report_kinds ?? []).map((k) => <td key={k.value}><input type="checkbox" aria-label={`${role.label}: ${k.label}`} checked={(form.required_reports[role.value] ?? []).includes(k.value)} onChange={() => toggle(role.value, k.value)} /></td>)}
                  </tr>
                ))}
              </Table>
            </Section>
            <Section title="Сроки и пороги">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block"><span className="field-label">Отчёт сдаётся до (время последнего дня периода)</span><Input type="time" value={form.daily_report_due.slice(0, 5)} onChange={(e) => setForm({ ...form, daily_report_due: e.target.value })} /></label>
                <label className="block"><span className="field-label">Напоминать о дедлайне задачи за, часов</span><Input type="number" min={0} max={168} value={form.deadline_reminder_hours} onChange={(e) => setForm({ ...form, deadline_reminder_hours: Number(e.target.value) })} /></label>
                <label className="block"><span className="field-label">Группа проблемная, если посещаемость ниже, % (0 — выключено)</span><Input type="number" min={0} max={100} value={form.problem_group_attendance} onChange={(e) => setForm({ ...form, problem_group_attendance: Number(e.target.value) })} /></label>
              </div>
              <div className="mt-4 space-y-2 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={form.detect_staff_absence} onChange={(e) => setForm({ ...form, detect_staff_absence: e.target.checked })} />Создавать проблему, если сотрудник не отметил приход в рабочий день</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={form.operations_director_sees_marketing_budget} onChange={(e) => setForm({ ...form, operations_director_sees_marketing_budget: e.target.checked })} />Операционный директор видит бюджеты маркетинга и CPL</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={form.notify_telegram} onChange={(e) => setForm({ ...form, notify_telegram: e.target.checked })} />Дублировать уведомления в Telegram (нужна настройка бота на сервере)</label>
              </div>
            </Section>
            <Note>Пороги «частых пропусков» студентов — из «Контроля активности» ассистента (одна настройка для всей LMS). Статусы KPI тренеров — из KPI Engine академии.</Note>
            <div className="flex justify-end"><Button isLoading={save.isPending} onClick={() => save.mutate(form, { onSuccess: () => showToast('Настройки сохранены', 'success'), onError: (e) => showToast(extractErrorMessage(e), 'error') })}>Сохранить</Button></div>
          </div>
        ) : null}
      </QueryView>
    </div>
  )
}
