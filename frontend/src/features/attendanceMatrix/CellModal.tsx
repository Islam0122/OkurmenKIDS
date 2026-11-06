import { useEffect, useState } from 'react'
import { History, Lock } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useMatrixCell, useUpdateMatrixCell } from '@/hooks/useAttendanceMatrix'
import { extractErrorMessage } from '@/lib/apiError'
import type { CellDetail, CellUpdate, MatrixAttendance } from '@/types/attendanceMatrix'
import { cn } from '@/utils/cn'

import { CellIcon, HOMEWORK_LABEL, formatDateTime } from './ui'
import type { CellCode } from '@/types/attendanceMatrix'

const ATTENDANCE_OPTIONS: { value: MatrixAttendance; label: string; code: CellCode }[] = [
  { value: 'present', label: 'Присутствовал', code: 'done' },
  { value: 'late', label: 'Опоздал', code: 'partial' },
  { value: 'excused', label: 'Уваж. причина', code: 'excused' },
  { value: 'absent', label: 'Без причины', code: 'absent' },
]

export interface CellTarget {
  lesson: number
  student: number
}

export function CellModal({ target, onClose }: { target: CellTarget | null; onClose: () => void }) {
  const { data, isPending, isError, refetch } = useMatrixCell(target?.lesson, target?.student)
  return (
    <Modal isOpen={target !== null} onClose={onClose} title={data ? data.student.name : 'Отметка'} size="md">
      {isPending ? <LoadingState label="Загружаем отметку…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data ? <CellForm key={`${data.lesson.id}-${data.student.id}`} cell={data} onClose={onClose} /> : null}
    </Modal>
  )
}

function CellForm({ cell, onClose }: { cell: CellDetail; onClose: () => void }) {
  const { showToast } = useToast()
  const save = useUpdateMatrixCell()
  const [attendance, setAttendance] = useState<MatrixAttendance | null>(cell.attendance)
  const [reason, setReason] = useState(cell.excuse_reason)
  const [comment, setComment] = useState(cell.comment)
  const [homework, setHomework] = useState(cell.homework)
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    setAttendance(cell.attendance)
    setReason(cell.excuse_reason)
    setComment(cell.comment)
    setHomework(cell.homework)
  }, [cell])

  const full = cell.edit_level === 'full'
  const canComment = cell.edit_level !== 'none'
  const hasHomework = cell.homeworks.length > 0 && !cell.homework_not_required
  const needsReason = attendance === 'excused' && !reason.trim()

  const submit = () => {
    const payload: CellUpdate = { lesson: cell.lesson.id, student: cell.student.id, comment }
    if (full) {
      payload.attendance = attendance
      payload.excuse_reason = attendance === 'excused' ? reason : ''
      if (hasHomework && (homework === 'done' || homework === 'missed') && homework !== cell.homework) payload.homework = homework
    }
    save.mutate(payload, {
      onSuccess: () => {
        showToast('Отметка сохранена', 'success')
        onClose()
      },
      onError: (error) => showToast(extractErrorMessage(error, 'Не удалось сохранить отметку'), 'error'),
    })
  }

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl bg-surface-muted p-3 text-sm">
        <Info label="Группа" value={cell.group.name} />
        <Info label="Дата урока" value={`${formatDay(cell.lesson.date)} · ${cell.lesson.start}–${cell.lesson.end}`} />
        <Info label="Тема" value={cell.lesson.topic || `Занятие ${cell.lesson.number}`} />
        <Info label="Тренер" value={cell.lesson.teacher || '—'} />
      </dl>

      {!full ? (
        <p className="flex items-start gap-2 rounded-lg border border-border px-3 py-2 text-sm text-ink-secondary">
          <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
          {cell.edit_level === 'comment' ? 'Вы можете только оставить комментарий.' : cell.edit_reason || 'Только просмотр.'}
        </p>
      ) : null}

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink">Посещаемость</legend>
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Посещаемость">
          {ATTENDANCE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={attendance === option.value}
              disabled={!full}
              onClick={() => setAttendance(option.value)}
              className={cn(
                'flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed',
                attendance === option.value ? 'border-brand-500 bg-brand-50 font-medium text-ink' : 'border-border text-ink-secondary hover:bg-surface-hover',
              )}
            >
              <CellIcon code={option.code} size="sm" />
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      {attendance === 'excused' ? (
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-ink">Причина отсутствия *</span>
          <input
            className="form-control"
            value={reason}
            maxLength={255}
            disabled={!full}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Например: болел, справка от врача"
          />
        </label>
      ) : null}

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink">Домашнее задание</legend>
        {hasHomework ? (
          <>
            <div className="flex gap-2" role="radiogroup" aria-label="Домашнее задание">
              {(['done', 'missed'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={homework === value}
                  disabled={!full}
                  onClick={() => setHomework(value)}
                  className={cn(
                    'flex-1 rounded-lg border px-3 py-2 text-sm transition-colors disabled:cursor-not-allowed',
                    homework === value
                      ? value === 'done' ? 'border-brand-500 bg-brand-50 font-medium text-brand-700' : 'border-danger bg-danger-soft font-medium text-danger'
                      : 'border-border text-ink-secondary hover:bg-surface-hover',
                  )}
                >
                  {HOMEWORK_LABEL[value]}
                </button>
              ))}
            </div>
            <ul className="mt-2 space-y-1 text-xs text-ink-muted">
              {cell.homeworks.map((hw) => (
                <li key={hw.id}>
                  {hw.title}
                  {hw.deadline ? ` · до ${formatDay(hw.deadline)}` : ''} — {hw.status_display}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-ink-muted">{HOMEWORK_LABEL.none}</p>
        )}
      </fieldset>

      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-ink">Комментарий тренера</span>
        <Textarea rows={2} maxLength={255} value={comment} disabled={!canComment} onChange={(e) => setComment(e.target.value)} />
      </label>

      <p className="text-xs text-ink-muted">
        Изменил: {cell.updated_by?.name ?? '—'} · {formatDateTime(cell.updated_at)}
      </p>

      {showHistory ? <HistoryList cell={cell} /> : null}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" size="sm" leftIcon={<History className="size-4" aria-hidden />} onClick={() => setShowHistory((v) => !v)}>
          {showHistory ? 'Скрыть историю' : `История (${cell.history.length})`}
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Отменить</Button>
          {canComment ? (
            <Button onClick={submit} isLoading={save.isPending} disabled={(full && (attendance === null || needsReason)) || save.isPending}>
              Сохранить
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function HistoryList({ cell }: { cell: CellDetail }) {
  if (cell.history.length === 0) return <p className="text-sm text-ink-muted">Изменений через журнал ещё не было.</p>
  return (
    <ol className="max-h-56 space-y-3 overflow-y-auto rounded-lg border border-border p-3">
      {cell.history.map((entry) => (
        <li key={entry.id} className="text-sm">
          <p className="text-xs text-ink-muted">
            {formatDateTime(entry.at)} · {entry.actor?.name ?? 'Система'}
          </p>
          <ul>
            {entry.changes.map((change) => (
              <li key={change.field} className="text-ink-secondary">
                <span className="font-medium text-ink">{change.label}:</span> {change.before} → {change.after}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="truncate text-ink">{value}</dd>
    </div>
  )
}

function formatDay(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`
}
