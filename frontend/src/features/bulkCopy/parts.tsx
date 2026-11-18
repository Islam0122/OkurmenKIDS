import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Check, RotateCcw } from 'lucide-react'

import { bulkCopyApi } from '@/api/bulkCopy'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import type {
  AttValues, BulkLesson, BulkOperation, BulkOptions, BulkPair, BulkPreview, BulkRecord, HwValues, RecordAction,
} from '@/types/bulkCopy'
import { cn } from '@/utils/cn'
import { formatDate } from '@/utils/format'

export const KEY = ['bulk-copy'] as const

export interface Side {
  group: number | null
  subject: number | null
  start: string
  end: string
}

export function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">{label}</label>
      {children}
    </div>
  )
}

/** Group → subject → period for one side (source or target). */
export function SideCard({ prefix, title, side, groups, onChange, extra }: {
  prefix: 'src' | 'tgt'; title: string; side: Side; groups: BulkOptions['groups']; onChange: (side: Side) => void; extra?: ReactNode
}) {
  const subjects = useQuery({
    queryKey: [...KEY, 'subjects', side.group],
    queryFn: () => bulkCopyApi.options(side.group!),
    enabled: side.group !== null,
  })
  return (
    <Card title={title} actions={extra}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={`${prefix}-group`} label="Группа">
          <Select id={`${prefix}-group`} value={side.group ? String(side.group) : ''} placeholder="Выберите группу"
            options={groups.map((g) => ({ value: String(g.id), label: g.name }))}
            onChange={(e) => onChange({ ...side, group: e.target.value ? Number(e.target.value) : null, subject: null })} />
        </Field>
        <Field id={`${prefix}-subject`} label="Предмет">
          <Select id={`${prefix}-subject`} value={side.subject ? String(side.subject) : ''} disabled={!side.group}
            placeholder={subjects.isFetching ? 'Загружаем…' : 'Выберите предмет'}
            options={(subjects.data?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
            onChange={(e) => onChange({ ...side, subject: e.target.value ? Number(e.target.value) : null })} />
        </Field>
        <Field id={`${prefix}-start`} label="Период: с">
          <DatePicker id={`${prefix}-start`} value={side.start} onChange={(e) => onChange({ ...side, start: e.target.value })} />
        </Field>
        <Field id={`${prefix}-end`} label="по">
          <DatePicker id={`${prefix}-end`} value={side.end} onChange={(e) => onChange({ ...side, end: e.target.value })} />
        </Field>
      </div>
    </Card>
  )
}

export function lessonLabel(lesson: BulkLesson) {
  return `${formatDate(lesson.date, false)}${lesson.start ? ` ${lesson.start}` : ''}${lesson.topic ? ` · ${lesson.topic}` : ''}`
}

/** Explicit source → target lesson mapping: one row per source lesson. */
export function LessonMapping({ preview, map, onChange, onAuto }: {
  preview: BulkPreview; map: Record<number, number | null>; onChange: (source: number, target: number | null) => void; onAuto: () => void
}) {
  const pairBySource = new Map<number, BulkPair>(preview.pairs.map((p) => [p.source, p]))
  const targets = preview.target_lessons
  return (
    <Card padding="none" title="Сопоставление занятий"
      description="Номера и даты уроков не обязаны совпадать — выберите целевое занятие для каждого занятия-источника."
      actions={<Button size="sm" variant="secondary" onClick={onAuto}><RotateCcw className="size-4" aria-hidden />По порядку</Button>}>
      {preview.source_lessons.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-ink-secondary">В периоде-источнике нет занятий по этому предмету.</p>
      ) : (
        <ol className="divide-y divide-border border-t border-border">
          {preview.source_lessons.map((lesson, i) => {
            const pair = pairBySource.get(lesson.id)
            const target = map[lesson.id] ?? null
            const problem = pair && target === pair.target ? pair.problem : null
            const hwProblem = pair && target === pair.target && pair.valid ? pair.homework_problem : null
            return (
              <li key={lesson.id} className="grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center sm:px-5">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-ink-muted">Источник · {i + 1}</p>
                  <p className="truncate text-sm font-medium text-ink">{lessonLabel(lesson)}</p>
                </div>
                <ArrowRight className="hidden size-4 text-ink-muted sm:block" aria-hidden />
                <div className="min-w-0">
                  <label htmlFor={`map-${lesson.id}`} className="sr-only">Целевое занятие для {lessonLabel(lesson)}</label>
                  <Select id={`map-${lesson.id}`} value={target ? String(target) : ''} placeholder="— не копировать"
                    options={targets.map((t) => ({ value: String(t.id), label: lessonLabel(t) }))}
                    onChange={(e) => onChange(lesson.id, e.target.value ? Number(e.target.value) : null)}
                    className={cn(problem && 'border-danger')} />
                  {problem ? <p className="mt-1 flex items-start gap-1 text-xs text-danger"><AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />{problem}</p> : null}
                  {hwProblem ? <p className="mt-1 text-xs text-warning">{hwProblem}</p> : null}
                  {pair && pair.valid && target === pair.target && pair.homework_pairs ? (
                    <p className="mt-1 flex items-center gap-1 text-xs text-brand-700"><Check className="size-3.5" aria-hidden />ДЗ сопоставлено: {pair.homework_pairs}</p>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}

const ACTION: Record<RecordAction, { label: string; tone: BadgeTone; cell: string }> = {
  create: { label: 'Будет скопировано', tone: 'success', cell: 'bg-brand-50 text-brand-700 ring-brand-200' },
  overwrite: { label: 'Перезапись', tone: 'warning', cell: 'bg-warning-soft text-warning ring-warning/30' },
  unchanged: { label: 'Уже совпадает', tone: 'muted', cell: 'bg-surface-muted text-ink-muted ring-border' },
  skip_existing: { label: 'Сохраняется', tone: 'info', cell: 'bg-info-soft text-info ring-info/20' },
  empty: { label: 'Пусто в источнике', tone: 'muted', cell: 'bg-surface text-ink-muted ring-border border-dashed' },
  invalid: { label: 'Ошибка данных', tone: 'danger', cell: 'bg-danger-soft text-danger ring-danger/20' },
}
export const ACTION_LEGEND = ACTION

const ATT_SHORT: Record<string, string> = { present: 'П', late: 'Оп', absent: 'Н', excused: 'У' }

function cellText(rec: BulkRecord): string {
  const v = (rec.after ?? rec.source ?? rec.target) as AttValues | HwValues | null
  if (!v) return '—'
  if (rec.kind === 'attendance') return ATT_SHORT[(v as AttValues).status] ?? '?'
  const hw = v as HwValues
  return hw.score !== null && hw.score !== undefined ? String(hw.score) : 'ДЗ'
}

/** Students × mapped lessons; each cell = what happens to that record. */
export function RecordMatrix({ preview }: { preview: BulkPreview }) {
  const pairs = preview.pairs.filter((p) => p.valid)
  const students = preview.students.filter((s) => s.status === 'matched')
  const byKey = new Map<string, BulkRecord[]>()
  for (const r of preview.records) {
    const key = `${r.student}:${r.pair}`
    byKey.set(key, [...(byKey.get(key) ?? []), r])
  }
  const lessons = new Map(preview.target_lessons.map((l) => [l.id, l]))
  if (!pairs.length || !students.length) {
    return <p className="px-5 pb-5 text-sm text-ink-secondary">Нет сопоставленных студентов или занятий.</p>
  }
  return (
    <div className="overflow-x-auto border-t border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-muted text-left text-xs font-medium text-ink-secondary">
          <tr>
            <th className="sticky left-0 z-10 bg-surface-muted px-4 py-2.5">Студент</th>
            {pairs.map((p) => {
              const lesson = lessons.get(p.target)
              return <th key={p.index} className="whitespace-nowrap px-2 py-2.5 text-center">{lesson ? formatDate(lesson.date, false) : p.target}</th>
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {students.map((s) => (
            <tr key={s.id}>
              <th scope="row" className="sticky left-0 z-10 bg-surface px-4 py-2 text-left font-medium text-ink">
                <span className="block max-w-44 truncate">{s.name}</span>
                <span className="block text-xs font-normal text-ink-muted">ID {s.id}</span>
              </th>
              {pairs.map((p) => (
                <td key={p.index} className="px-2 py-2 text-center">
                  <div className="flex flex-wrap justify-center gap-1">
                    {(byKey.get(`${s.id}:${p.index}`) ?? []).map((r, i) => (
                      <span key={i} title={`${r.kind === 'attendance' ? 'Посещаемость' : `ДЗ «${r.homework}»`}: ${ACTION[r.action].label}${r.problem ? ` — ${r.problem}` : ''}`}
                        className={cn('inline-flex min-w-8 items-center justify-center rounded-md px-1.5 py-1 text-xs font-semibold tabular-nums ring-1', ACTION[r.action].cell)}>
                        {cellText(r)}
                      </span>
                    ))}
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const STATUS_TONE: Record<BulkOperation['status'], BadgeTone> = {
  queued: 'info', running: 'info', applied: 'success', failed: 'danger', reverted: 'muted', partially_reverted: 'warning',
}
const CATEGORY_LABEL = { attendance: 'посещаемость', homework: 'ДЗ', scores: 'оценки' } as const

export function HistoryCard({ onUndo }: { onUndo: (op: BulkOperation) => void }) {
  const history = useQuery({
    queryKey: [...KEY, 'history'],
    queryFn: () => bulkCopyApi.history(),
    // Poll while a background copy is still running.
    refetchInterval: (q) => (q.state.data?.results.some((op) => op.status === 'queued' || op.status === 'running') ? 3000 : false),
  })
  const ops = history.data?.results ?? []
  return (
    <Card padding="none" title="Журнал операций"
      description="Отмена восстанавливает прежние значения только там, где после копирования ничего не меняли.">
      {history.isPending ? <div className="p-5"><LoadingState /></div> : history.isError ? (
        <div className="p-5"><ErrorState onRetry={() => void history.refetch()} /></div>
      ) : ops.length === 0 ? <p className="px-5 pb-5 text-sm text-ink-secondary">Операций ещё не было.</p> : (
        <ul className="divide-y divide-border border-t border-border">
          {ops.map((op) => (
            <li key={op.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-ink">
                    {op.source.group} · {op.source.subject} <ArrowRight className="inline size-3.5" aria-hidden /> {op.target.group} · {op.target.subject}
                  </p>
                  <Badge tone={STATUS_TONE[op.status]}>{op.status_label}</Badge>
                </div>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {new Date(op.created_at).toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })} · {op.created_by}
                  {' · '}{op.categories.map((c) => CATEGORY_LABEL[c]).join(', ')}
                </p>
                <p className="mt-1 text-sm text-ink-secondary">
                  {op.status === 'failed' ? <span className="text-danger">{op.error}</span> : (
                    <>Создано {op.copied} · перезаписано {op.overwritten} · пропущено {op.skipped}
                      {op.reverted_by ? ` · отменил ${op.reverted_by}` : ''}
                      {(op.revert_details.skipped_changed ?? 0) > 0 ? ` (не тронуто изменённых позже: ${op.revert_details.skipped_changed})` : ''}</>
                  )}
                </p>
              </div>
              {op.can_undo ? (
                <Button size="sm" variant="secondary" className="self-start sm:self-center" onClick={() => onUndo(op)}>
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
