import { useState } from 'react'
import { ArrowRightLeft, UserCheck, UserX } from 'lucide-react'

import { assistantApi } from '@/api/assistant'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useAssistantFormMutation, useAssistantOptions } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { BulkAction, BulkResult, Ref, StudentStatus } from '@/types/assistant'

import { Field, FormError, ModalActions, todayIso } from '../ui'

/** The bit of a student every quick action needs. */
export interface StudentLite {
  id: number
  full_name: string
  status: StudentStatus
  group: Ref | null
}

const PAUSE = 'pause'

/** Group choices for a target group: open groups, with free seats shown. */
function useGroupOptions(excludeId?: number) {
  const { data } = useAssistantOptions()
  return (data?.groups ?? [])
    .filter((group) => group.id !== excludeId)
    .map((group) => ({
      value: String(group.id),
      label: `${group.name} — ${group.course} (${group.students_count}${group.max_students ? `/${group.max_students}` : ''})`,
    }))
}

function ReasonSelect({ value, onChange, id }: { value: string; onChange: (value: string) => void; id: string }) {
  const { data } = useAssistantOptions()
  const options = [{ value: PAUSE, label: 'Пауза (вернётся позже)' }, ...(data?.deactivation_reasons ?? [])]
  return <Select id={id} value={value} onChange={(event) => onChange(event.target.value)} options={options} placeholder="Выберите причину" />
}

export function DeactivateModal({ student, onClose }: { student: StudentLite; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const [date, setDate] = useState(todayIso())
  const [returnDate, setReturnDate] = useState('')
  const [comment, setComment] = useState('')
  const mutation = useAssistantFormMutation(
    () => assistantApi.deactivate(student.id, {
      reason, event_date: date || null, comment, expected_return_date: reason === PAUSE && returnDate ? returnDate : null,
    }),
    reason === PAUSE ? `${student.full_name}: поставлен(а) на паузу` : `${student.full_name}: студент деактивирован`,
  )
  const commentRequired = reason === 'other'
  const canSubmit = reason !== '' && (!commentRequired || comment.trim() !== '')

  return (
    <Modal isOpen onClose={onClose} title="Деактивировать студента" icon={<UserX className="size-5 text-danger" aria-hidden />}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (canSubmit) mutation.mutate(undefined, { onSuccess: onClose })
        }}
        className="space-y-4"
      >
        <div className="rounded-lg bg-surface-muted px-3 py-2 text-sm">
          <p className="font-medium text-ink">{student.full_name}</p>
          <p className="text-ink-secondary">{student.group?.name ?? 'Без группы'}</p>
        </div>
        <Field label="Причина" htmlFor="deactivate-reason" required>
          <ReasonSelect id="deactivate-reason" value={reason} onChange={setReason} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={reason === PAUSE ? 'Дата начала паузы' : 'Дата деактивации'} htmlFor="deactivate-date">
            <DatePicker id="deactivate-date" value={date} max={todayIso()} onChange={(event) => setDate(event.target.value)} />
          </Field>
          {reason === PAUSE ? (
            <Field label="Ожидаемая дата возвращения" htmlFor="deactivate-return">
              <DatePicker id="deactivate-return" value={returnDate} min={todayIso()} onChange={(event) => setReturnDate(event.target.value)} />
            </Field>
          ) : null}
        </div>
        <Field label="Комментарий" htmlFor="deactivate-comment" required={commentRequired}>
          <Textarea id="deactivate-comment" rows={3} value={comment} onChange={(event) => setComment(event.target.value)} />
        </Field>
        <p className="text-xs text-ink-secondary">Студент не удаляется: посещаемость, ДЗ, стипендии и история сохраняются.</p>
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" variant="danger" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending}>
            {reason === PAUSE ? 'Поставить на паузу' : 'Деактивировать'}
          </Button>
        </ModalActions>
      </form>
    </Modal>
  )
}

export function ActivateModal({ student, onClose }: { student: StudentLite; onClose: () => void }) {
  const fromPause = student.status === 'paused'
  const [group, setGroup] = useState(student.group ? String(student.group.id) : '')
  const [date, setDate] = useState(todayIso())
  const groups = useGroupOptions()
  const mutation = useAssistantFormMutation(
    () => assistantApi.activate(student.id, { group: group ? Number(group) : null, event_date: date || null }),
    `${student.full_name}: студент активирован`,
  )
  const canSubmit = fromPause || group !== ''

  return (
    <Modal isOpen onClose={onClose} title="Активировать студента" icon={<UserCheck className="size-5 text-brand-600" aria-hidden />}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (canSubmit) mutation.mutate(undefined, { onSuccess: onClose })
        }}
        className="space-y-4"
      >
        <div className="rounded-lg bg-surface-muted px-3 py-2 text-sm">
          <p className="font-medium text-ink">{student.full_name}</p>
          <p className="text-ink-secondary">{fromPause ? 'Возвращается после паузы' : 'Повторная активация после ухода'}</p>
        </div>
        <Field label="Группа" htmlFor="activate-group" required={!fromPause} hint={fromPause ? 'Пусто — остаётся в текущей группе.' : undefined}>
          <Select id="activate-group" value={group} onChange={(event) => setGroup(event.target.value)} options={groups} placeholder="Выберите группу" />
        </Field>
        <Field label="Дата начала" htmlFor="activate-date">
          <DatePicker id="activate-date" value={date} onChange={(event) => setDate(event.target.value)} />
        </Field>
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending}>Активировать</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}

export function TransferModal({ student, onClose }: { student: StudentLite; onClose: () => void }) {
  const [group, setGroup] = useState('')
  const [date, setDate] = useState(todayIso())
  const [comment, setComment] = useState('')
  const groups = useGroupOptions(student.group?.id)
  const target = groups.find((option) => option.value === group)
  const mutation = useAssistantFormMutation(
    () => assistantApi.transfer(student.id, { group: Number(group), event_date: date || null, comment }),
    `${student.full_name}: ${student.group?.name ?? 'без группы'} → ${target?.label.split(' — ')[0] ?? ''}`,
  )

  return (
    <Modal isOpen onClose={onClose} title="Перевести студента" icon={<ArrowRightLeft className="size-5 text-brand-600" aria-hidden />}>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (group) mutation.mutate(undefined, { onSuccess: onClose })
        }}
        className="space-y-4"
      >
        <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-muted px-3 py-2 text-sm">
          <div className="min-w-0">
            <dt className="field-label">Студент</dt>
            <dd className="truncate font-medium text-ink">{student.full_name}</dd>
          </div>
          <div className="min-w-0">
            <dt className="field-label">Текущая группа</dt>
            <dd className="truncate font-medium text-ink">{student.group?.name ?? 'Без группы'}</dd>
          </div>
        </dl>
        <Field label="Новая группа" htmlFor="transfer-group" required>
          <Select id="transfer-group" value={group} onChange={(event) => setGroup(event.target.value)} options={groups} placeholder="Выберите группу" />
        </Field>
        <Field label="Дата перевода" htmlFor="transfer-date">
          <DatePicker id="transfer-date" value={date} onChange={(event) => setDate(event.target.value)} />
        </Field>
        <Field label="Причина" htmlFor="transfer-comment">
          <Textarea id="transfer-comment" rows={2} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Например: удобнее время занятий" />
        </Field>
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={!group || mutation.isPending} isLoading={mutation.isPending}>Перевести</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}

const BULK_TITLES: Record<BulkAction, string> = {
  transfer: 'Перевести студентов',
  add_to_group: 'Добавить в группу',
  deactivate: 'Деактивировать студентов',
  activate: 'Активировать студентов',
}

/** One workflow for several selected students; the result is shown per student. */
export function BulkActionModal({
  action,
  students,
  presetGroup,
  onClose,
  onDone,
}: {
  action: BulkAction
  students: StudentLite[]
  presetGroup?: Ref
  onClose: () => void
  onDone?: () => void
}) {
  const [group, setGroup] = useState(presetGroup ? String(presetGroup.id) : '')
  const [reason, setReason] = useState('')
  const [date, setDate] = useState(todayIso())
  const [comment, setComment] = useState('')
  const [result, setResult] = useState<BulkResult | null>(null)
  const groups = useGroupOptions()
  const needsGroup = action === 'transfer' || action === 'add_to_group'
  const mutation = useAssistantFormMutation(
    () => assistantApi.bulk({
      action, students: students.map((s) => s.id), group: group ? Number(group) : null,
      reason: reason || undefined, event_date: date || null, comment,
    }),
    (res) => (res.failed ? `Готово: ${res.done}, не выполнено: ${res.failed}` : `Готово: ${res.done}`),
  )
  const canSubmit = (!needsGroup || group !== '') && (action !== 'deactivate' || reason !== '') &&
    (action !== 'deactivate' || reason !== 'other' || comment.trim() !== '')

  return (
    <Modal isOpen onClose={onClose} title={BULK_TITLES[action]} size="lg">
      {result ? (
        <div className="space-y-3">
          <p className="text-sm text-ink">
            Выполнено: <b>{result.done}</b>{result.failed ? <>, не выполнено: <b className="text-danger">{result.failed}</b></> : null}
          </p>
          <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-lg border border-border">
            {result.results.map((row) => (
              <li key={row.id} className="flex items-start justify-between gap-3 px-3 py-2 text-sm">
                <span className="font-medium text-ink">{row.name}</span>
                <span className={row.ok ? 'text-brand-700' : 'text-right text-danger'}>{row.ok ? 'Готово' : row.error}</span>
              </li>
            ))}
          </ul>
          <ModalActions>
            <Button onClick={() => { onDone?.(); onClose() }}>Закрыть</Button>
          </ModalActions>
        </div>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (canSubmit) mutation.mutate(undefined, { onSuccess: setResult })
          }}
          className="space-y-4"
        >
          <p className="text-sm text-ink-secondary">
            Выбрано студентов: <b className="text-ink">{students.length}</b> — {students.slice(0, 5).map((s) => s.full_name).join(', ')}
            {students.length > 5 ? ` и ещё ${students.length - 5}` : ''}
          </p>
          {needsGroup ? (
            <Field label="Группа" htmlFor="bulk-group" required>
              <Select id="bulk-group" value={group} onChange={(event) => setGroup(event.target.value)} options={groups} placeholder="Выберите группу" />
            </Field>
          ) : null}
          {action === 'deactivate' ? (
            <Field label="Причина" htmlFor="bulk-reason" required>
              <ReasonSelect id="bulk-reason" value={reason} onChange={setReason} />
            </Field>
          ) : null}
          {action === 'activate' ? (
            <Field label="Группа" htmlFor="bulk-group" hint="Обязательна для деактивированных; для студентов на паузе — по желанию.">
              <Select id="bulk-group" value={group} onChange={(event) => setGroup(event.target.value)} options={groups} placeholder="Текущая группа" />
            </Field>
          ) : null}
          <Field label="Дата" htmlFor="bulk-date">
            <DatePicker id="bulk-date" value={date} max={action === 'deactivate' ? todayIso() : undefined} onChange={(event) => setDate(event.target.value)} />
          </Field>
          <Field label="Комментарий" htmlFor="bulk-comment" required={action === 'deactivate' && reason === 'other'}>
            <Textarea id="bulk-comment" rows={2} value={comment} onChange={(event) => setComment(event.target.value)} />
          </Field>
          <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
          <ModalActions>
            <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
            <Button type="submit" variant={action === 'deactivate' ? 'danger' : 'primary'} disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending}>
              {BULK_TITLES[action]}
            </Button>
          </ModalActions>
        </form>
      )}
    </Modal>
  )
}
