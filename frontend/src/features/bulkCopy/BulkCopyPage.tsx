import { useEffect, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import {
  AlertTriangle, CopyPlus, FileWarning, Layers, Link2Off, ShieldAlert, UserCheck, UserX, Wallet,
} from 'lucide-react'

import { bulkCopyApi, newOperationId } from '@/api/bulkCopy'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import type { BulkCategory, BulkOperation, BulkParams } from '@/types/bulkCopy'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/format'

import { ACTION_LEGEND, HistoryCard, KEY, LessonMapping, RecordMatrix, SideCard, type Side } from './parts'

/**
 * «Массовое копирование» (/app/bulk-copy): attendance, homework results and
 * homework scores from one group / subject / period to another, with an
 * explicit lesson mapping, a live server preview, confirmed execution,
 * an audit log and safe undo (backend: apps.bulk_copy).
 */

type Preset = 'all' | 'attendance' | 'homework' | 'scores'
const PRESET_CATEGORIES: Record<Preset, BulkCategory[]> = {
  all: ['attendance', 'homework', 'scores'], attendance: ['attendance'], homework: ['homework'], scores: ['scores'],
}

function monthBounds(): [string, string] {
  const now = new Date()
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), iso(now)]
}

export function BulkCopyPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [start, end] = monthBounds()

  const [source, setSource] = useState<Side>({ group: null, subject: null, start, end })
  const [target, setTarget] = useState<Side>({ group: null, subject: null, start, end })
  const [preset, setPreset] = useState<Preset>('all')
  const [mode, setMode] = useState<'all' | 'selected'>('all')
  const [selected, setSelected] = useState<number[]>([])
  const [conflict, setConflict] = useState<'preserve' | 'overwrite'>('preserve')
  const [skipEmpty, setSkipEmpty] = useState(true)
  const [copyComments, setCopyComments] = useState(false)
  // source lesson id → target lesson id (null = not copied); undefined until the server suggests one.
  const [map, setMap] = useState<Record<number, number | null> | undefined>(undefined)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [ack, setAck] = useState(false)
  const [operationId, setOperationId] = useState(newOperationId)
  const [undoTarget, setUndoTarget] = useState<BulkOperation | null>(null)

  const options = useQuery({ queryKey: [...KEY, 'options'], queryFn: () => bulkCopyApi.options() })

  const sidesReady = Boolean(source.group && source.subject && target.group && target.subject
    && source.start && source.end && target.start && target.end)
  const selectionEmpty = mode === 'selected' && selected.length === 0
  const lessonMap = map === undefined ? null
    : Object.entries(map).filter(([, t]) => t !== null).map(([s, t]) => ({ source: Number(s), target: t as number }))
  const params: BulkParams | null = sidesReady ? {
    source_group: source.group!, source_subject: source.subject!, source_start: source.start, source_end: source.end,
    target_group: target.group!, target_subject: target.subject!, target_start: target.start, target_end: target.end,
    categories: PRESET_CATEGORIES[preset], lesson_map: lessonMap,
    mode: selectionEmpty ? 'all' : mode, student_ids: mode === 'selected' ? [...selected].sort((a, b) => a - b) : [],
    conflict, skip_empty: skipEmpty, copy_comments: copyComments,
  } : null

  const preview = useQuery({
    queryKey: [...KEY, 'preview', params],
    queryFn: () => bulkCopyApi.preview(params!),
    enabled: params !== null,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const plan = params ? preview.data : undefined

  // The first preview of a selection carries the server's suggested mapping — start from it.
  useEffect(() => {
    if (map === undefined && plan && params?.lesson_map === null) {
      setMap(Object.fromEntries(plan.source_lessons.map((l) => [l.id, plan.pairs.find((p) => p.source === l.id)?.target ?? null])))
    }
  }, [map, plan, params?.lesson_map])

  const resetMapping = () => { setMap(undefined); setSelected([]) }
  const changeSource = (s: Side) => { setSource(s); resetMapping() }
  const changeTarget = (s: Side) => { setTarget(s); resetMapping() }

  const apply = useMutation({
    mutationFn: () => bulkCopyApi.apply({ ...params!, fingerprint: plan!.fingerprint, operation_id: operationId, confirm_overwrite: ack }),
    onSuccess: (op) => {
      setConfirmOpen(false)
      setAck(false)
      setOperationId(newOperationId())
      showToast(op.status === 'queued'
        ? 'Операция поставлена в очередь — результат появится в журнале.'
        : `Скопировано: создано ${op.copied}, перезаписано ${op.overwritten}`, 'success')
      void queryClient.invalidateQueries({ queryKey: KEY })
    },
    onError: (error) => {
      setConfirmOpen(false)
      if (isAxiosError(error) && error.response?.status === 409) void preview.refetch()
      showToast(extractErrorMessage(error), 'error')
      void queryClient.invalidateQueries({ queryKey: [...KEY, 'history'] })
    },
  })

  const undo = useMutation({
    mutationFn: (id: number) => bulkCopyApi.undo(id),
    onSuccess: (op) => {
      setUndoTarget(null)
      const kept = (op.revert_details.skipped_changed ?? 0) + (op.revert_details.skipped_missing ?? 0)
      showToast(kept ? `Отменено. Не тронуто изменённых позже записей: ${kept}` : 'Операция отменена', kept ? 'info' : 'success')
      void queryClient.invalidateQueries({ queryKey: KEY })
    },
    onError: (error) => { setUndoTarget(null); showToast(extractErrorMessage(error), 'error') },
  })

  const s = plan?.summary
  const canApply = Boolean(s && s.to_copy > 0 && !selectionEmpty && !preview.isFetching)
  const previewError = preview.isError && params ? extractErrorMessage(preview.error) : null
  const groups = options.data?.groups ?? []
  const listed = (plan?.students ?? []).filter((st) => st.status !== 'no_source_records' || mode === 'selected')

  return (
    <div>
      <PageHeader title="Массовое копирование данных"
        description="Посещаемость, результаты и оценки за домашние задания — из одной группы, предмета и периода в другие. Сначала предпросмотр, потом подтверждение." />

      {options.isPending ? <LoadingState /> : options.isError ? <ErrorState onRetry={() => void options.refetch()} /> : (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <SideCard prefix="src" title="Откуда" side={source} groups={groups} onChange={changeSource} />
            <SideCard prefix="tgt" title="Куда" side={target} groups={groups} onChange={changeTarget}
              extra={source.group ? (
                <Button size="sm" variant="ghost" onClick={() => changeTarget({ ...target, group: source.group, subject: null })}>Та же группа</Button>
              ) : undefined} />
          </div>

          <Card title="Что и как копировать">
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="min-w-0">
                <p className="mb-1.5 text-sm font-medium text-ink">Данные</p>
                <SegmentedControl aria-label="Какие данные" value={preset} onChange={setPreset}
                  options={[{ value: 'all', label: 'Всё' }, { value: 'attendance', label: 'Посещаемость' },
                    { value: 'homework', label: 'Домашние задания' }, { value: 'scores', label: 'Оценки' }]} />
                <p className="mt-1.5 text-xs text-ink-muted">Оценки — баллы за ДЗ (0–10). Сами задания, экзамены и личные данные не копируются.</p>
              </div>
              <div className="min-w-0">
                <p className="mb-1.5 text-sm font-medium text-ink">Записи</p>
                <SegmentedControl aria-label="Какие записи" value={mode} onChange={setMode}
                  options={[{ value: 'all', label: 'Все студенты' }, { value: 'selected', label: 'Выбранные' }]} />
              </div>
              <div className="min-w-0">
                <p className="mb-1.5 text-sm font-medium text-ink">Если запись в цели уже есть</p>
                <SegmentedControl aria-label="Существующие записи" value={conflict} onChange={setConflict}
                  options={[{ value: 'preserve', label: 'Сохранить' }, { value: 'overwrite', label: 'Перезаписать' }]} />
                {conflict === 'overwrite' ? <p className="mt-1.5 text-xs font-medium text-warning">Перезапись потребует отдельного подтверждения.</p> : null}
              </div>
              <div className="flex min-w-0 flex-col justify-end gap-2">
                <label className="flex items-center gap-2.5 text-sm text-ink">
                  <input type="checkbox" className="size-4 accent-brand-600" checked={skipEmpty} onChange={(e) => setSkipEmpty(e.target.checked)} />
                  Пропускать пустые значения (не стирать оценку или комментарий в цели)
                </label>
                <label className="flex items-center gap-2.5 text-sm text-ink">
                  <input type="checkbox" className="size-4 accent-brand-600" checked={copyComments} onChange={(e) => setCopyComments(e.target.checked)} />
                  Копировать комментарии тренера
                </label>
              </div>
            </div>
          </Card>

          {!params ? (
            <EmptyState icon={CopyPlus} title="Выберите группу, предмет и период для источника и цели"
              description="Затем проверьте сопоставление занятий — предпросмотр обновляется сразу, до подтверждения ничего не меняется." />
          ) : previewError && !plan ? (
            <div role="alert" className="card flex items-start gap-3 p-4 text-sm text-danger"><AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />{previewError}</div>
          ) : !plan || !s ? <LoadingState label="Готовим предпросмотр…" /> : (
            <section aria-label="Предпросмотр" aria-busy={preview.isFetching} className={cn('space-y-6 transition-opacity', preview.isFetching && 'opacity-60')}>
              {previewError ? <div role="alert" className="card flex items-start gap-3 p-4 text-sm text-danger"><AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />{previewError}</div> : null}

              {map ? (
                <LessonMapping preview={plan} map={map}
                  onChange={(src, tgt) => setMap((m) => ({ ...(m ?? {}), [src]: tgt }))}
                  onAuto={() => setMap(undefined)} />
              ) : null}

              <StatGrid columns={4}>
                <StatCard label="Сопоставлено студентов" value={s.students_matched} icon={UserCheck}
                  hint={s.students_without_source ? `без данных в источнике: ${s.students_without_source}` : undefined} />
                <StatCard label="Не сопоставлено" value={s.students_unmatched} icon={UserX} tone={s.students_unmatched ? 'warning' : 'default'}
                  hint="нет в целевой группе" />
                <StatCard label="Записей к копированию" value={s.to_copy} icon={Layers}
                  hint={`посещаемость ${s.attendance} · ДЗ ${s.homework_results}`} />
                <StatCard label="Будет перезаписано" value={s.overwrite} icon={ShieldAlert} tone={s.overwrite ? 'danger' : 'default'} />
                <StatCard label="Пустые в источнике" value={s.empty} icon={FileWarning} />
                <StatCard label="Уже есть в цели" value={s.existing_target} icon={Layers}
                  hint={`сохраняются ${s.skip_existing} · совпадают ${s.unchanged}`} />
                <StatCard label="Неверные сопоставления" value={s.invalid_pairs + s.homework_problems} icon={Link2Off}
                  tone={s.invalid_pairs ? 'warning' : 'default'} hint={s.invalid_records ? `ошибок в данных: ${s.invalid_records}` : undefined} />
              </StatGrid>

              {s.billing_lessons > 0 ? (
                <div className="card flex items-start gap-3 border-warning/40 bg-warning-soft/50 p-4 text-sm text-ink-secondary">
                  <Wallet className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
                  <p>Посещаемость будет записана на {s.billing_lessons} {pluralize(s.billing_lessons, 'занятие', 'занятия', 'занятий')}. Как и при ручной отметке, это пересчитает списания уроков в биллинге; отмена операции пересчитает их обратно.</p>
                </div>
              ) : null}

              {listed.length ? (
                <Card title="Студенты" description="Сопоставление только по записи студента в базе (ID). Не сопоставлен — студента нет в целевой группе.">
                  <ul className="flex flex-wrap gap-2">
                    {listed.map((st) => {
                      const choosable = mode === 'selected' && (st.status === 'matched' || st.status === 'not_selected')
                      return (
                        <li key={st.id}>
                          <label className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm',
                            st.status === 'not_in_target_group' ? 'border-danger/30 bg-danger-soft/40 text-danger'
                              : st.status === 'no_source_records' ? 'border-border text-ink-muted' : 'border-border text-ink')}>
                            {choosable ? (
                              <input type="checkbox" className="size-4 accent-brand-600" checked={selected.includes(st.id)}
                                onChange={() => setSelected((ids) => (ids.includes(st.id) ? ids.filter((x) => x !== st.id) : [...ids, st.id]))} />
                            ) : null}
                            {st.name}<span className="text-xs text-ink-muted">ID {st.id}</span>
                            {st.status === 'not_in_target_group' ? <span className="text-xs">· {st.group ?? 'без группы'}</span> : null}
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                  {selectionEmpty ? <p className="mt-3 text-sm text-warning">Отметьте хотя бы одного студента.</p> : null}
                </Card>
              ) : null}

              <Card padding="none" title="Записи по занятиям"
                description="П — присутствовал, Оп — опоздал, Н — не был, У — уважительная; число — оценка за ДЗ."
                actions={(
                  <Button onClick={() => { setAck(false); setConfirmOpen(true) }} disabled={!canApply}>
                    <CopyPlus className="size-4" aria-hidden />Скопировать {s.to_copy || ''}
                  </Button>
                )}>
                <div className="flex flex-wrap gap-2 px-4 pb-3 sm:px-5">
                  {Object.entries(ACTION_LEGEND).map(([k, v]) => <Badge key={k} tone={v.tone}>{v.label}</Badge>)}
                </div>
                <RecordMatrix preview={plan} />
              </Card>
            </section>
          )}

          <HistoryCard onUndo={setUndoTarget} />
        </div>
      )}

      <Modal isOpen={confirmOpen} onClose={() => setConfirmOpen(false)} title="Подтвердите копирование" icon={<CopyPlus className="size-5" aria-hidden />}>
        {s ? (
          <div className="space-y-4 text-sm text-ink-secondary">
            <ul className="space-y-1">
              <li>Новых записей: <b className="text-ink">{s.create}</b></li>
              <li>Перезапись: <b className={s.overwrite ? 'text-danger' : 'text-ink'}>{s.overwrite}</b></li>
              <li>Пропущено: <b className="text-ink">{s.empty + s.skip_existing + s.unchanged + s.invalid_records}</b>, неверных сопоставлений: <b className="text-ink">{s.invalid_pairs}</b></li>
            </ul>
            {s.overwrite ? (
              <label className="flex items-start gap-2.5 rounded-xl bg-danger-soft p-3 text-danger">
                <input type="checkbox" className="mt-0.5 size-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                <span>Я понимаю, что {s.overwrite} {pluralize(s.overwrite, 'существующая запись будет заменена', 'существующие записи будут заменены', 'существующих записей будут заменены')}.</span>
              </label>
            ) : null}
            <p className="text-xs text-ink-muted">Всё выполняется одной операцией: при любой ошибке ничего не меняется. Операцию можно отменить в журнале.</p>
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setConfirmOpen(false)}>Отмена</Button>
              <Button variant={s.overwrite ? 'danger' : 'primary'} isLoading={apply.isPending} disabled={Boolean(s.overwrite) && !ack}
                onClick={() => apply.mutate()}>Скопировать</Button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog isOpen={undoTarget !== null} title="Отменить операцию?" tone="danger" confirmLabel="Отменить операцию"
        message="Созданные записи будут удалены, перезаписанные — восстановлены. Записи, изменённые после копирования, останутся как есть."
        isLoading={undo.isPending} onConfirm={() => undoTarget && undo.mutate(undoTarget.id)} onCancel={() => setUndoTarget(null)} />
    </div>
  )
}
