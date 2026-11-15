import { useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Download, KeyRound, RotateCcw, ShieldCheck, UsersRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useToast } from '@/components/ui/Toast'
import { ASSISTANT_KEY, useAssistantOptions, useBulkCreate, useBulkPreview, useBulkRetry, useBulkRun, useBulkRuns } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { BulkExportState, BulkRun, BulkScope } from '@/types/assistant'
import { cn } from '@/utils/cn'

/**
 * «Кабинеты учеников» — Assistant Workspace → Студенты → Кабинеты.
 *
 * Creates portal accounts for active students who do not have one yet
 * (backend: apps.portal.services.bulk_accounts). The page drives a run in
 * small steps, so a long batch never waits on one request. The temporary
 * passwords exist only in the one-time Excel file, which is downloaded from
 * here right after the batch — the page never shows them.
 */

const EXPORT_TONE: Record<BulkExportState, BadgeTone> = {
  none: 'muted',
  ready: 'success',
  downloaded: 'info',
  expired: 'danger',
}

const STEP_SIZE = 10

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}>
      <div className="h-full rounded-full bg-brand-500 transition-[width] duration-300" style={{ width: `${value}%` }} />
    </div>
  )
}

function ScopeCard({
  active,
  title,
  description,
  icon: Icon,
  onClick,
}: {
  active: boolean
  title: string
  description: string
  icon: typeof UsersRound
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex w-full items-start gap-3 rounded-2xl border p-4 text-left transition-colors',
        active ? 'border-brand-400 bg-brand-50/70 ring-1 ring-brand-300' : 'border-border bg-surface hover:border-brand-200 hover:bg-surface-hover',
      )}
    >
      <span className={cn('grid size-10 shrink-0 place-items-center rounded-xl', active ? 'bg-brand-500 text-white' : 'bg-surface-muted text-ink-secondary')}>
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">{title}</span>
        <span className="mt-0.5 block text-sm text-ink-secondary">{description}</span>
      </span>
    </button>
  )
}

function RunResults({
  run,
  onDownload,
  onRetry,
  onResume,
  downloading,
  retrying,
  running,
}: {
  run: BulkRun
  onDownload: () => void
  onRetry: () => void
  onResume: () => void
  downloading: boolean
  retrying: boolean
  running: boolean
}) {
  const { counts, export: exportInfo } = run
  const unfinished = run.status !== 'completed' && counts.pending > 0
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="font-medium text-ink">
            Пакет №{run.id} · {run.scope_label}
          </p>
          <div className="flex items-center gap-2">
            <Badge tone={unfinished ? 'info' : 'success'}>{unfinished ? `Не завершён · ${run.progress}%` : 'Завершён'}</Badge>
            {unfinished && !running ? (
              <Button size="sm" onClick={onResume}>Продолжить пакет</Button>
            ) : null}
          </div>
        </div>
        <ProgressBar value={run.progress} />
      </div>

      <StatGrid columns={4}>
        <StatCard label="Всего активных студентов" value={counts.total} icon={UsersRound} />
        <StatCard label="Аккаунт уже был" value={counts.existing} icon={ShieldCheck} />
        <StatCard label="Создано новых" value={counts.created} icon={CheckCircle2} tone="default" />
        <StatCard label="С ошибкой" value={counts.failed} icon={AlertTriangle} tone={counts.failed > 0 ? 'danger' : 'default'} />
      </StatGrid>

      <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">Выгрузка учётных данных</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-ink-secondary">
            <Badge tone={EXPORT_TONE[exportInfo.state]}>{exportInfo.label}</Badge>
            {exportInfo.state === 'ready' ? 'Файл Excel можно скачать один раз. Пароли нигде не сохраняются в открытом виде.' : null}
            {exportInfo.state === 'downloaded' ? 'Файл уже выгружен. Пароли удалены из системы.' : null}
            {exportInfo.state === 'expired' ? 'Срок хранения истёк. Для этих студентов сбросьте пароль в карточке студента.' : null}
            {exportInfo.state === 'none' && counts.created === 0 ? 'В этом пакете новых аккаунтов не создано.' : null}
          </p>
        </div>
        <Button
          leftIcon={<Download className="size-4" aria-hidden />}
          onClick={onDownload}
          isLoading={downloading}
          disabled={!exportInfo.downloadable}
        >
          Скачать Excel
        </Button>
      </div>

      {counts.failed > 0 ? (
        <Card
          title="Ошибки"
          description="Студенты, для которых аккаунт не создан. Повтор создаёт аккаунты только для них — уже созданные не трогаются."
          actions={
            <Button variant="secondary" leftIcon={<RotateCcw className="size-4" aria-hidden />} onClick={onRetry} isLoading={retrying} disabled={unfinished || running}>
              Повторить неудачные
            </Button>
          }
        >
          <div className="max-h-80 overflow-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-muted text-left text-xs font-semibold tracking-wide text-ink-muted uppercase">
                <tr>
                  <th className="px-3 py-2">Студент</th>
                  <th className="px-3 py-2">Группа</th>
                  <th className="px-3 py-2">Причина</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {run.failed.map((row) => (
                  <tr key={row.id}>
                    <td className="px-3 py-2 font-medium text-ink">{row.full_name}</td>
                    <td className="px-3 py-2 text-ink-secondary">{row.group || '—'}</td>
                    <td className="px-3 py-2 text-danger">{row.reason || 'Неизвестная ошибка'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {run.created.length > 0 ? (
        <Card title="Созданные аккаунты" description="Логины — пароли только в Excel.">
          <div className="max-h-72 overflow-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-muted text-left text-xs font-semibold tracking-wide text-ink-muted uppercase">
                <tr>
                  <th className="px-3 py-2">Студент</th>
                  <th className="px-3 py-2">Группа</th>
                  <th className="px-3 py-2">Логин</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {run.created.map((row) => (
                  <tr key={`${row.student_id}-${row.login}`}>
                    <td className="px-3 py-2 text-ink">{row.full_name}</td>
                    <td className="px-3 py-2 text-ink-secondary">{row.group || '—'}</td>
                    <td className="px-3 py-2 font-mono text-ink">{row.login}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
    </div>
  )
}

export function AssistantBulkAccountsPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const { data: options } = useAssistantOptions()
  const [scope, setScope] = useState<BulkScope>('all')
  const [groupIds, setGroupIds] = useState<number[]>([])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [activeId, setActiveId] = useState<number | undefined>(undefined)
  const [running, setRunning] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const driving = useRef(false)

  const previewEnabled = scope === 'all' || groupIds.length > 0
  const preview = useBulkPreview(scope, scope === 'groups' ? groupIds : [], previewEnabled)
  const runs = useBulkRuns()
  const creating = useBulkCreate()
  const retry = useBulkRetry()
  const latestId = runs.data?.results[0]?.id
  const shownId = activeId ?? latestId
  const runQuery = useBulkRun(shownId)
  const run = runQuery.data
  const exportable = run?.export.downloadable ?? false

  const groups = useMemo(() => options?.groups ?? [], [options])

  const refreshAll = () => queryClient.invalidateQueries({ queryKey: ASSISTANT_KEY })

  /** Runs the batch to the end: one short step at a time, each updating the page. */
  const drive = async (start: BulkRun) => {
    if (driving.current) return
    driving.current = true
    setRunning(true)
    setActiveId(start.id)
    queryClient.setQueryData([...ASSISTANT_KEY, 'bulk-run', start.id], start)
    let current = start
    try {
      while (current.counts.pending > 0) {
        current = await assistantApi.bulkProcess(current.id, STEP_SIZE)
        queryClient.setQueryData([...ASSISTANT_KEY, 'bulk-run', current.id], current)
      }
      showToast(`Пакет №${current.id} завершён: создано ${current.counts.created}, ошибок ${current.counts.failed}.`, 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      driving.current = false
      setRunning(false)
      await refreshAll()
    }
  }

  const startBatch = async () => {
    setConfirmOpen(false)
    try {
      const created = await creating.mutateAsync({ scope, groupIds })
      await drive(created)
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    }
  }

  const retryFailed = async () => {
    if (!run) return
    setRetrying(true)
    try {
      const next = await retry.mutateAsync(run.id)
      await drive(next)
    } catch {
      /* the mutation already shows the API's message */
    } finally {
      setRetrying(false)
    }
  }

  const download = async () => {
    if (!run) return
    setDownloading(true)
    try {
      const blob = await assistantApi.bulkExport(run.id)
      saveBlob(blob, `okurmen_kids_accounts_run${run.id}.xlsx`)
      showToast('Файл Excel скачан. Выдайте логины и пароли и не пересылайте файл по открытым каналам.', 'success')
      await refreshAll()
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setDownloading(false)
    }
  }

  const resume = () => {
    if (run) void drive(run)
  }

  const toggleGroup = (id: number) => {
    setGroupIds((current) => (current.includes(id) ? current.filter((g) => g !== id) : [...current, id]))
  }

  const pv = preview.data
  const canStart = Boolean(pv && pv.to_create > 0) && !running && !creating.isPending

  return (
    <div>
      <PageHeader
        title="Кабинеты учеников"
        description="Создание логинов и временных паролей для студентов, у которых ещё нет кабинета."
        actions={
          <Link to="/assistant/students" className="inline-flex h-9 items-center rounded-lg px-3 text-sm font-medium text-brand-700 hover:bg-brand-50">
            ← К списку студентов
          </Link>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <Card title="1. Кого создать" description="Только активные студенты. Существующие кабинеты не меняются, пароли не сбрасываются.">
          <div className="space-y-3">
            <ScopeCard
              active={scope === 'all'}
              title="Все активные студенты"
              description="Каждому студенту без кабинета — свой логин и временный пароль."
              icon={UsersRound}
              onClick={() => setScope('all')}
            />
            <ScopeCard
              active={scope === 'groups'}
              title="Выбранные группы"
              description="Выберите одну или несколько групп. Одна группа — тот же процесс."
              icon={KeyRound}
              onClick={() => setScope('groups')}
            />
            {scope === 'groups' ? (
              <div className="flex flex-wrap gap-2 pt-1" role="group" aria-label="Группы">
                {groups.length === 0 ? <p className="text-sm text-ink-secondary">Групп пока нет.</p> : null}
                {groups.map((group) => {
                  const selected = groupIds.includes(group.id)
                  return (
                    <button
                      key={group.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => toggleGroup(group.id)}
                      className={cn(
                        'h-8 rounded-full border px-3 text-sm font-medium transition-colors',
                        selected ? 'border-brand-500 bg-brand-500 text-white' : 'border-border bg-surface text-ink-secondary hover:border-brand-300',
                      )}
                    >
                      {group.name}
                      <span className={cn('ml-1.5 text-xs', selected ? 'text-white/80' : 'text-ink-muted')}>{group.students_count}</span>
                    </button>
                  )
                })}
              </div>
            ) : null}
          </div>
        </Card>

        <Card title="2. Что произойдёт" description="Предпросмотр — ничего не записывается, пока вы не подтвердите.">
          {!previewEnabled ? (
            <EmptyState icon={UsersRound} title="Выберите группы" description="Отметьте хотя бы одну группу, чтобы увидеть предпросмотр." className="py-6" />
          ) : preview.isPending ? (
            <LoadingState label="Считаем…" />
          ) : preview.isError ? (
            <ErrorState onRetry={() => void preview.refetch()} />
          ) : pv ? (
            <div className="space-y-4">
              <StatGrid columns={3}>
                <StatCard label="Студентов в охвате" value={pv.total} icon={UsersRound} />
                <StatCard label="Уже с кабинетом" value={pv.existing} icon={ShieldCheck} />
                <StatCard label="Будет создано" value={pv.to_create} icon={KeyRound} />
              </StatGrid>
              {pv.students.length > 0 ? (
                <div className="max-h-64 overflow-auto rounded-xl border border-border">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-surface-muted text-left text-xs font-semibold tracking-wide text-ink-muted uppercase">
                      <tr>
                        <th className="px-3 py-2">Студент</th>
                        <th className="px-3 py-2">Группа</th>
                        <th className="px-3 py-2">Логин</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {pv.students.map((row) => (
                        <tr key={row.id}>
                          <td className="px-3 py-2 text-ink">{row.full_name}</td>
                          <td className="px-3 py-2 text-ink-secondary">{row.group || '—'}</td>
                          <td className="px-3 py-2">
                            {row.has_account ? <Badge tone="muted">Уже есть: {row.login}</Badge> : <span className="font-mono text-ink">{row.login}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-ink-secondary">В выбранной области нет активных студентов.</p>
              )}
              <div className="flex flex-wrap items-center justify-end gap-2">
                {pv.to_create === 0 && pv.total > 0 ? <p className="mr-auto text-sm text-ink-secondary">Все студенты уже имеют кабинет.</p> : null}
                <Button onClick={() => setConfirmOpen(true)} disabled={!canStart} leftIcon={<KeyRound className="size-4" aria-hidden />}>
                  Создать аккаунты ({pv.to_create})
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      </div>

      <div className="mt-6">
        <Card
          title="3. Результат и выгрузка"
          description="Пароли показываются только в Excel — один раз, сразу после создания."
          actions={
            <Button
              variant="secondary"
              leftIcon={<Download className="size-4" aria-hidden />}
              onClick={() => void download()}
              disabled={!exportable || running}
              isLoading={downloading}
            >
              Экспорт учётных данных в Excel
            </Button>
          }
        >
          {running && !run ? <LoadingState label="Запускаем пакет…" /> : null}
          {!run && !running ? (
            <EmptyState icon={CheckCircle2} title="Пакетов пока не было" description="Создайте аккаунты — здесь появятся результаты и файл Excel." className="py-8" />
          ) : null}
          {run ? (
            <RunResults
              run={run}
              onDownload={() => void download()}
              onRetry={() => void retryFailed()}
              onResume={resume}
              downloading={downloading}
              retrying={retrying}
              running={running}
            />
          ) : null}
        </Card>
      </div>

      {runs.data && runs.data.results.length > 1 ? (
        <div className="mt-6">
          <Card title="История пакетов" description="Последние запуски. Открыть результат можно в любой момент; файл Excel — только если он ещё не выгружен.">
            <ul className="divide-y divide-border">
              {runs.data.results.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setActiveId(item.id)}
                    className={cn('flex w-full flex-wrap items-center justify-between gap-2 py-2.5 text-left text-sm hover:text-brand-700', item.id === shownId && 'font-semibold text-brand-700')}
                  >
                    <span>
                      Пакет №{item.id} · {item.scope_label}
                      <span className="ml-2 text-ink-muted">{new Date(item.created_at).toLocaleString('ru-RU')}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge tone="success">{item.counts.created} создано</Badge>
                      {item.counts.failed > 0 ? <Badge tone="danger">{item.counts.failed} ошибок</Badge> : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={confirmOpen}
        title="Создать аккаунты?"
        message={`Будут созданы аккаунты для ${pv?.to_create ?? 0} студентов без кабинета. Существующие кабинеты и пароли не изменятся. Временные пароли будут доступны только в Excel — скачайте его сразу после создания.`}
        confirmLabel="Создать"
        isLoading={creating.isPending}
        onConfirm={() => void startBatch()}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
