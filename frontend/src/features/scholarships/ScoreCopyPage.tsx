import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import {
  AlertTriangle, ArrowRight, CheckCircle2, ClipboardCopy, History, RotateCcw, ShieldAlert, UserX, Users,
} from 'lucide-react'

import { newOperationId, scoreCopyApi } from '@/api/scoreCopy'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import type {
  ScoreCopyAction, ScoreCopyConflict, ScoreCopyMode, ScoreCopyOperation, ScoreCopyParams, ScoreCopyPeriod,
  ScoreCopyPreview, ScoreCopyRow, ScoreValues,
} from '@/types/scoreCopy'
import { cn } from '@/utils/cn'
import { formatDate, pluralize } from '@/utils/format'

/**
 * «Копирование оценок между предметами» (/app/scholarships/copy-scores).
 *
 * Trainer scores (scholarships.TrainerFeedback) of one subject are copied to
 * another for a group. The preview is a dry run of the real server plan and
 * refreshes whenever a parameter changes; «Скопировать» sends that plan's
 * fingerprint, so the server refuses if anything changed in between. Students
 * are matched by their database id only (backend services.score_copy).
 */

const KEY = ['scholarships', 'score-copy'] as const

const ACTION: Record<ScoreCopyAction, { label: string; tone: BadgeTone }> = {
  create: { label: 'Будет скопировано', tone: 'success' },
  overwrite: { label: 'Перезапись', tone: 'warning' },
  unchanged: { label: 'Уже совпадает', tone: 'muted' },
  skip_existing: { label: 'Оценка сохраняется', tone: 'info' },
  skip_empty: { label: 'Нет оценки-источника', tone: 'muted' },
  unmatched_ambiguous_source: { label: 'Не сопоставлено', tone: 'danger' },
  unmatched_no_target: { label: 'Не сопоставлено', tone: 'danger' },
  unmatched_ambiguous_target: { label: 'Не сопоставлено', tone: 'danger' },
  not_selected: { label: 'Не выбран', tone: 'muted' },
}

const STATUS_TONE: Record<ScoreCopyOperation['status'], BadgeTone> = {
  applied: 'success',
  reverted: 'muted',
  partially_reverted: 'warning',
}

function periodLabel(p: ScoreCopyPeriod) {
  return `${p.title || 'Стипендия'} · ${formatDate(p.period_start, false)} — ${formatDate(p.period_end)}${p.is_draft ? '' : ' · утверждён'}`
}

function Scores({ values, muted = false }: { values: ScoreValues | Omit<ScoreValues, 'score'> | null; muted?: boolean }) {
  if (!values) return <span className="text-ink-muted">—</span>
  const score = 'score' in values ? values.score : null
  return (
    <span className={cn('inline-flex flex-col', muted && 'text-ink-secondary')}>
      <span className="font-semibold tabular-nums text-ink">
        {values.progress}·{values.participation}·{values.discipline}·{values.understanding}
      </span>
      {score !== null && score !== undefined ? <span className="text-xs tabular-nums text-ink-muted">{score.toFixed(2)} / 100</span> : null}
    </span>
  )
}

function Field({ id, label, children, hint }: { id: string; label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      {children}
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

const num = (value: string) => (value ? Number(value) : null)

export function ScoreCopyPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const [group, setGroup] = useState<number | null>(null)
  const [sourceSubject, setSourceSubject] = useState<number | null>(null)
  const [targetSubject, setTargetSubject] = useState<number | null>(null)
  const [sourcePeriod, setSourcePeriod] = useState<number | null>(null)
  const [targetPeriod, setTargetPeriod] = useState<number | null>(null)
  const [mode, setMode] = useState<ScoreCopyMode>('all')
  const [selected, setSelected] = useState<number[]>([])
  const [conflict, setConflict] = useState<ScoreCopyConflict>('preserve')
  const [copyComment, setCopyComment] = useState(false)
  const [sourceTeacher, setSourceTeacher] = useState<number | null>(null)
  const [targetTeacher, setTargetTeacher] = useState<number | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [overwriteAck, setOverwriteAck] = useState(false)
  const [result, setResult] = useState<ScoreCopyOperation | null>(null)

  const options = useQuery({ queryKey: [...KEY, 'options', group], queryFn: () => scoreCopyApi.options(group ?? undefined),
    placeholderData: keepPreviousData })
  const periods = options.data?.periods ?? []
  const subjects = group ? options.data?.subjects ?? [] : []

  const ready = Boolean(group && sourceSubject && targetSubject && sourcePeriod && targetPeriod)
  const selectionEmpty = mode === 'selected' && selected.length === 0
  const params: ScoreCopyParams | null = ready ? {
    group: group!, source_subject: sourceSubject!, target_subject: targetSubject!, source_period: sourcePeriod!,
    target_period: targetPeriod!,
    // With nothing ticked yet the full list is shown so students can be picked; «Скопировать» stays off.
    mode: selectionEmpty ? 'all' : mode, student_ids: mode === 'selected' ? [...selected].sort((a, b) => a - b) : [],
    conflict, copy_comment: copyComment, source_teacher: sourceTeacher, target_teacher: targetTeacher,
  } : null

  const preview = useQuery({
    queryKey: [...KEY, 'preview', params],
    queryFn: () => scoreCopyApi.preview(params!),
    enabled: params !== null,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const plan: ScoreCopyPreview | undefined = params ? preview.data : undefined

  const history = useQuery({ queryKey: [...KEY, 'history'], queryFn: () => scoreCopyApi.history() })

  // One id per intended operation: a retry of the same click is applied once by the server.
  const [operationId, setOperationId] = useState(newOperationId)
  const apply = useMutation({
    mutationFn: () => scoreCopyApi.apply({
      ...params!, fingerprint: plan!.fingerprint, operation_id: operationId, confirm_overwrite: overwriteAck,
    }),
    onSuccess: (operation) => {
      setResult(operation)
      setConfirmOpen(false)
      setOverwriteAck(false)
      setOperationId(newOperationId())
      showToast(`Скопировано: ${operation.copied}, перезаписано: ${operation.overwritten}`, 'success')
      void queryClient.invalidateQueries({ queryKey: KEY })
      void queryClient.invalidateQueries({ queryKey: ['scholarships'] })
    },
    onError: (error) => {
      setConfirmOpen(false)
      if (isAxiosError(error) && error.response?.status === 409) void preview.refetch()
      showToast(extractErrorMessage(error), 'error')
    },
  })
  const [undoTarget, setUndoTarget] = useState<ScoreCopyOperation | null>(null)
  const undo = useMutation({
    mutationFn: (id: number) => scoreCopyApi.undo(id),
    onSuccess: (operation) => {
      setUndoTarget(null)
      const kept = (operation.revert_details.skipped_changed ?? 0) + (operation.revert_details.skipped_missing ?? 0)
      showToast(kept ? `Отменено. Не тронуто изменённых вручную оценок: ${kept}` : 'Копирование отменено', kept ? 'info' : 'success')
      void queryClient.invalidateQueries({ queryKey: KEY })
      void queryClient.invalidateQueries({ queryKey: ['scholarships'] })
    },
    onError: (error) => {
      setUndoTarget(null)
      showToast(extractErrorMessage(error), 'error')
    },
  })

  const resetPlan = () => { setResult(null); setSelected([]); setSourceTeacher(null); setTargetTeacher(null) }
  const toggle = (id: number) => setSelected((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))

  const summary = plan?.summary
  const canApply = Boolean(plan && summary && summary.copyable > 0 && !selectionEmpty && !preview.isFetching)
  const rows = plan?.rows ?? []
  const needsSourceTeacher = rows.some((r) => r.action === 'unmatched_ambiguous_source') || (plan?.source_teachers.length ?? 0) > 1
  const needsTargetTeacher = rows.some((r) => r.action === 'unmatched_ambiguous_target') || (plan?.target_teachers.length ?? 0) > 1
  const sourceName = subjects.find((s) => s.id === sourceSubject)?.name ?? ''
  const targetName = subjects.find((s) => s.id === targetSubject)?.name ?? ''

  const previewError = preview.isError && params ? extractErrorMessage(preview.error) : null

  const sortedRows = useMemo(() => {
    const order: ScoreCopyAction[] = ['overwrite', 'create', 'unmatched_ambiguous_source', 'unmatched_ambiguous_target',
      'unmatched_no_target', 'skip_existing', 'skip_empty', 'unchanged', 'not_selected']
    return [...rows].sort((a, b) => order.indexOf(a.action) - order.indexOf(b.action))
  }, [rows])

  return (
    <div>
      <BackLink to="/app/scholarships">Стипендии</BackLink>
      <PageHeader
        title="Копирование оценок между предметами"
        description="Перенесите оценки тренера одного предмета в другой предмет группы — с предпросмотром, журналом и отменой."
      />

      {options.isPending ? <LoadingState /> : options.isError ? (
        <ErrorState onRetry={() => void options.refetch()} />
      ) : (
        <div className="space-y-6">
          <Card title="Что копируем" description="Студенты сопоставляются только по их записи в базе — не по имени и не по порядку строк.">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field id="sc-group" label="Группа">
                <Select id="sc-group" value={group ? String(group) : ''} placeholder="Выберите группу"
                  options={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
                  onChange={(e) => { setGroup(num(e.target.value)); setSourceSubject(null); setTargetSubject(null); resetPlan() }} />
              </Field>
              <Field id="sc-source-subject" label="Предмет-источник">
                <Select id="sc-source-subject" value={sourceSubject ? String(sourceSubject) : ''} disabled={!group}
                  placeholder="Откуда" options={subjects.map((s) => ({ value: String(s.id), label: s.name }))}
                  onChange={(e) => { setSourceSubject(num(e.target.value)); resetPlan() }} />
              </Field>
              <Field id="sc-target-subject" label="Целевой предмет">
                <Select id="sc-target-subject" value={targetSubject ? String(targetSubject) : ''} disabled={!group}
                  placeholder="Куда" options={subjects.map((s) => ({ value: String(s.id), label: s.name }))}
                  onChange={(e) => { setTargetSubject(num(e.target.value)); resetPlan() }} />
              </Field>
              <Field id="sc-source-period" label="Период-источник">
                <Select id="sc-source-period" value={sourcePeriod ? String(sourcePeriod) : ''} placeholder="Выберите период"
                  options={periods.map((p) => ({ value: String(p.id), label: periodLabel(p) }))}
                  onChange={(e) => {
                    const id = num(e.target.value)
                    setSourcePeriod(id)
                    // Most copies stay within one period — prefill the target when it is open.
                    if (!targetPeriod && periods.find((p) => p.id === id)?.is_draft) setTargetPeriod(id)
                    resetPlan()
                  }} />
              </Field>
              <Field id="sc-target-period" label="Целевой период" hint="Только неутверждённые периоды.">
                <Select id="sc-target-period" value={targetPeriod ? String(targetPeriod) : ''} placeholder="Выберите период"
                  options={periods.filter((p) => p.is_draft).map((p) => ({ value: String(p.id), label: periodLabel(p) }))}
                  onChange={(e) => { setTargetPeriod(num(e.target.value)); resetPlan() }} />
              </Field>
              <div className="flex items-end">
                <label className="flex min-h-10 cursor-pointer items-center gap-2.5 text-sm text-ink">
                  <input type="checkbox" className="size-4 accent-brand-600" checked={copyComment}
                    onChange={(e) => setCopyComment(e.target.checked)} />
                  Копировать и комментарий тренера
                </label>
              </div>
            </div>

            <div className="mt-5 grid gap-4 border-t border-border pt-5 md:grid-cols-2">
              <div>
                <p className="mb-1.5 text-sm font-medium text-ink">Студенты</p>
                <SegmentedControl aria-label="Какие студенты" value={mode} onChange={(v) => { setMode(v); setResult(null) }}
                  options={[{ value: 'all', label: 'Все студенты' }, { value: 'selected', label: 'Выбранные' }]} />
                <p className="mt-1.5 text-xs text-ink-muted">
                  {mode === 'selected' ? 'Отметьте студентов в таблице ниже.' : 'Студенты без оценки-источника всегда пропускаются — пустые значения ничего не стирают.'}
                </p>
              </div>
              <div>
                <p className="mb-1.5 text-sm font-medium text-ink">Если оценка уже есть</p>
                <SegmentedControl aria-label="Существующие оценки" value={conflict} onChange={(v) => { setConflict(v); setResult(null) }}
                  options={[{ value: 'preserve', label: 'Сохранить' }, { value: 'overwrite', label: 'Перезаписать' }]} />
                <p className={cn('mt-1.5 text-xs', conflict === 'overwrite' ? 'font-medium text-warning' : 'text-ink-muted')}>
                  {conflict === 'overwrite' ? 'Перезапись потребует отдельного подтверждения.' : 'Существующие оценки не меняются.'}
                </p>
              </div>
            </div>

            {plan && (needsSourceTeacher || needsTargetTeacher) ? (
              <div className="mt-5 grid gap-4 rounded-xl bg-warning-soft/60 p-4 sm:grid-cols-2">
                {needsSourceTeacher ? (
                  <Field id="sc-source-teacher" label="Тренер-источник" hint="Предмет-источник оценивали несколько тренеров.">
                    <Select id="sc-source-teacher" value={sourceTeacher ? String(sourceTeacher) : ''} placeholder="Любой (если оценки совпадают)"
                      options={plan.source_teachers.map((t) => ({ value: String(t.id), label: t.name }))}
                      onChange={(e) => setSourceTeacher(num(e.target.value))} />
                  </Field>
                ) : null}
                {needsTargetTeacher ? (
                  <Field id="sc-target-teacher" label="Целевой тренер" hint="Целевой предмет вели несколько тренеров.">
                    <Select id="sc-target-teacher" value={targetTeacher ? String(targetTeacher) : ''} placeholder="Определить по занятиям"
                      options={plan.target_teachers.map((t) => ({ value: String(t.id), label: t.name }))}
                      onChange={(e) => setTargetTeacher(num(e.target.value))} />
                  </Field>
                ) : null}
              </div>
            ) : null}
          </Card>

          {!params ? (
            <EmptyState icon={ClipboardCopy} title="Выберите группу, предметы и периоды"
              description="Предпросмотр появится сразу — до подтверждения ничего не меняется." />
          ) : previewError && !plan ? (
            <div role="alert" className="card flex items-start gap-3 p-4 text-sm text-danger">
              <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />{previewError}
            </div>
          ) : !plan ? <LoadingState label="Готовим предпросмотр…" /> : (
            <section aria-label="Предпросмотр" className={cn('space-y-4 transition-opacity', preview.isFetching && 'opacity-60')} aria-busy={preview.isFetching}>
              {previewError ? (
                <div role="alert" className="card flex items-start gap-3 p-4 text-sm text-danger">
                  <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />{previewError}
                </div>
              ) : null}
              <StatGrid columns={3}>
                <StatCard label="Сопоставлено студентов" value={summary!.matched} icon={Users} hint={`из ${summary!.students}`} />
                <StatCard label="Будет скопировано" value={summary!.copyable} icon={CheckCircle2}
                  hint={summary!.unchanged ? `уже совпадают: ${summary!.unchanged}` : undefined} />
                <StatCard label="Пустые (нет оценки-источника)" value={summary!.empty} icon={ClipboardCopy} />
                <StatCard label="Уже есть целевая оценка" value={summary!.existing_target} icon={History}
                  hint={summary!.skip_existing ? `сохраняются: ${summary!.skip_existing}` : undefined} />
                <StatCard label="Не сопоставлено" value={summary!.unmatched} icon={UserX} tone={summary!.unmatched ? 'warning' : 'default'} />
                <StatCard label="Будет перезаписано" value={summary!.overwrite} icon={ShieldAlert} tone={summary!.overwrite ? 'danger' : 'default'} />
              </StatGrid>

              <Card padding="none" title={`${sourceName} → ${targetName}`}
                description="Критерии: прогресс · активность · дисциплина · понимание (1–5)."
                actions={(
                  <Button onClick={() => { setOverwriteAck(false); setConfirmOpen(true) }} disabled={!canApply}>
                    <ClipboardCopy className="size-4" aria-hidden />Скопировать {summary!.copyable ? summary!.copyable : ''}
                  </Button>
                )}>
                {selectionEmpty ? <p className="px-4 pb-2 text-sm text-warning sm:px-5">Отметьте хотя бы одного студента.</p> : null}
                <PreviewTable rows={sortedRows} selectable={mode === 'selected'} selected={selected} onToggle={toggle} />
              </Card>
            </section>
          )}

          {result ? <ResultCard operation={result} /> : null}

          <HistoryCard query={history} onUndo={setUndoTarget} />
        </div>
      )}

      <Modal isOpen={confirmOpen} onClose={() => setConfirmOpen(false)} title="Подтвердите копирование" icon={<ClipboardCopy className="size-5" aria-hidden />}>
        {summary ? (
          <div className="space-y-4 text-sm text-ink-secondary">
            <p>
              <b className="text-ink">{sourceName}</b> <ArrowRight className="inline size-4" aria-hidden /> <b className="text-ink">{targetName}</b>,
              группа <b className="text-ink">{options.data?.groups.find((g) => g.id === group)?.name}</b>.
            </p>
            <ul className="space-y-1">
              <li>Новых оценок: <b className="text-ink">{summary.create}</b></li>
              <li>Перезапись: <b className={summary.overwrite ? 'text-danger' : 'text-ink'}>{summary.overwrite}</b></li>
              <li>Пропущено: <b className="text-ink">{summary.empty + summary.skip_existing + summary.unmatched + summary.unchanged}</b></li>
            </ul>
            {summary.overwrite ? (
              <label className="flex items-start gap-2.5 rounded-xl bg-danger-soft p-3 text-danger">
                <input type="checkbox" className="mt-0.5 size-4 accent-[var(--color-danger)]" checked={overwriteAck}
                  onChange={(e) => setOverwriteAck(e.target.checked)} />
                <span>Я понимаю, что {summary.overwrite} {pluralize(summary.overwrite, 'существующая оценка будет заменена', 'существующие оценки будут заменены', 'существующих оценок будут заменены')}.</span>
              </label>
            ) : null}
            <p className="text-xs text-ink-muted">Всё выполняется одной операцией: при ошибке ничего не меняется. Рейтинг периода обновится после пересчёта. Операцию можно отменить в журнале.</p>
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setConfirmOpen(false)}>Отмена</Button>
              <Button onClick={() => apply.mutate()} isLoading={apply.isPending}
                disabled={Boolean(summary.overwrite) && !overwriteAck} variant={summary.overwrite ? 'danger' : 'primary'}>
                Скопировать
              </Button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        isOpen={undoTarget !== null}
        title="Отменить копирование?"
        message="Созданные оценки будут удалены, перезаписанные — восстановлены. Оценки, изменённые вручную после копирования, останутся как есть."
        confirmLabel="Отменить копирование"
        tone="danger"
        isLoading={undo.isPending}
        onConfirm={() => undoTarget && undo.mutate(undoTarget.id)}
        onCancel={() => setUndoTarget(null)}
      />
    </div>
  )
}

function PreviewTable({ rows, selectable, selected, onToggle }: {
  rows: ScoreCopyRow[]; selectable: boolean; selected: number[]; onToggle: (id: number) => void
}) {
  if (!rows.length) return <p className="px-5 pb-5 text-sm text-ink-secondary">В группе нет студентов с занятиями по этим предметам.</p>
  return (
    <>
      {/* Desktop / tablet: a table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="border-y border-border bg-surface-muted text-left text-xs font-medium text-ink-secondary">
            <tr>
              {selectable ? <th className="w-10 px-4 py-2.5"><span className="sr-only">Выбрать</span></th> : null}
              <th className="px-4 py-2.5">Студент</th>
              <th className="px-4 py-2.5">Источник</th>
              <th className="px-4 py-2.5">Сейчас в целевом</th>
              <th className="px-4 py-2.5">Станет</th>
              <th className="px-4 py-2.5">Итог</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => (
              <tr key={row.student_id} className={cn(row.action === 'overwrite' && 'bg-warning-soft/40')}>
                {selectable ? (
                  <td className="px-4 py-3">
                    <input type="checkbox" className="size-4 accent-brand-600" aria-label={`Выбрать: ${row.student_name}`}
                      checked={selected.includes(row.student_id)} onChange={() => onToggle(row.student_id)} />
                  </td>
                ) : null}
                <td className="px-4 py-3">
                  <p className="font-medium text-ink">{row.student_name}</p>
                  <p className="text-xs text-ink-muted">ID {row.student_id}{row.target_teacher ? ` · ${row.target_teacher.name}` : ''}</p>
                </td>
                <td className="px-4 py-3"><Scores values={row.source} /></td>
                <td className="px-4 py-3"><Scores values={row.target} muted /></td>
                <td className="px-4 py-3">{row.after ? <Scores values={row.after} /> : <span className="text-ink-muted">—</span>}</td>
                <td className="px-4 py-3">
                  <Badge tone={ACTION[row.action].tone}>{ACTION[row.action].label}</Badge>
                  {row.action.startsWith('unmatched') || row.action === 'skip_existing' ? (
                    <p className="mt-1 max-w-56 text-xs text-ink-muted">{row.reason}</p>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Phone: cards */}
      <ul className="divide-y divide-border border-t border-border md:hidden">
        {rows.map((row) => (
          <li key={row.student_id} className={cn('flex gap-3 p-4', row.action === 'overwrite' && 'bg-warning-soft/40')}>
            {selectable ? (
              <input type="checkbox" className="mt-1 size-5 shrink-0 accent-brand-600" aria-label={`Выбрать: ${row.student_name}`}
                checked={selected.includes(row.student_id)} onChange={() => onToggle(row.student_id)} />
            ) : null}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-medium text-ink">{row.student_name}</p>
                <Badge tone={ACTION[row.action].tone}>{ACTION[row.action].label}</Badge>
              </div>
              <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div><dt className="text-ink-muted">Источник</dt><dd><Scores values={row.source} /></dd></div>
                <div><dt className="text-ink-muted">Сейчас</dt><dd><Scores values={row.target} muted /></dd></div>
                <div><dt className="text-ink-muted">Станет</dt><dd>{row.after ? <Scores values={row.after} /> : '—'}</dd></div>
              </dl>
              {row.action.startsWith('unmatched') ? <p className="mt-1.5 text-xs text-ink-muted">{row.reason}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

function ResultCard({ operation }: { operation: ScoreCopyOperation }) {
  return (
    <div role="status" className="card flex flex-col gap-3 border-brand-200 bg-brand-50/60 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-brand-600" aria-hidden />
        <div>
          <p className="font-semibold text-ink">
            {operation.replayed ? 'Эта операция уже была выполнена' : 'Оценки скопированы'}
          </p>
          <p className="text-sm text-ink-secondary">
            Новых: {operation.copied} · перезаписано: {operation.overwritten} · пропущено: {operation.skipped}.
            Не забудьте пересчитать рейтинг периода.
          </p>
        </div>
      </div>
      <code className="self-start rounded-lg bg-surface px-2 py-1 text-xs text-ink-secondary">{operation.operation_id.slice(0, 8)}</code>
    </div>
  )
}

function HistoryCard({ query, onUndo }: {
  query: ReturnType<typeof useQuery<Awaited<ReturnType<typeof scoreCopyApi.history>>>>
  onUndo: (op: ScoreCopyOperation) => void
}) {
  const operations = query.data?.results ?? []
  return (
    <Card title="Журнал копирований" description="Кто, когда и что скопировал. Отмена не трогает оценки, изменённые вручную после копирования." padding="none">
      {query.isPending ? <div className="p-5"><LoadingState /></div> : query.isError ? (
        <div className="p-5"><ErrorState onRetry={() => void query.refetch()} /></div>
      ) : operations.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-ink-secondary">Копирований ещё не было.</p>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {operations.map((op) => (
            <li key={op.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-ink">{op.group.name}: {op.source_subject.name} → {op.target_subject.name}</p>
                  <Badge tone={STATUS_TONE[op.status]}>{op.status_label}</Badge>
                </div>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {new Date(op.created_at).toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })} · {op.created_by}
                  {op.target_period ? ` · ${formatDate(op.target_period.period_start, false)} — ${formatDate(op.target_period.period_end)}` : ''}
                </p>
                <p className="mt-1 text-sm text-ink-secondary">
                  Новых {op.copied} · перезаписано {op.overwritten} · пропущено {op.skipped}
                  {op.reverted_by ? ` · отменил ${op.reverted_by}` : ''}
                  {(op.revert_details.skipped_changed ?? 0) > 0 ? ` (не тронуто изменённых: ${op.revert_details.skipped_changed})` : ''}
                </p>
              </div>
              {op.can_undo ? (
                <Button variant="secondary" size="sm" onClick={() => onUndo(op)} className="self-start sm:self-center">
                  <RotateCcw className="size-4" aria-hidden />Отменить
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
