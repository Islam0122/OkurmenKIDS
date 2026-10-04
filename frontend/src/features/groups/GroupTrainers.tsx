import { useState } from 'react'
import { UserCog } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useAssignTrainer, useTrainerAssignments } from '@/hooks/useGroups'
import { extractErrorMessage } from '@/lib/apiError'
import type { TrainerAssignmentOverview, TrainerAssignmentProgram } from '@/types/academy'

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString('ru-RU') : '—'
}

/** «Тренеры группы» for Admin / Team Lead: who teaches each subject, who
 * assigned them and when, and «Назначить / Изменить тренера» — the Team
 * Lead's one academic write (backend: POST /groups/{id}/assign-trainer/,
 * a dedicated action; the trainer and the group themselves stay read-only). */
export function GroupTrainers({ groupId }: { groupId: number }) {
  const { data, isPending, isError, refetch } = useTrainerAssignments(groupId)
  const [target, setTarget] = useState<{ program: TrainerAssignmentProgram | null } | null>(null)

  if (isPending) return <LoadingState label="Загружаем тренеров группы…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />

  const active = data.programs.filter((p) => p.is_active)

  return (
    <section aria-label="Тренеры группы" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="section-title">👨‍🏫 Тренеры группы</h3>
        <Button size="sm" leftIcon={<UserCog className="size-4" aria-hidden />} onClick={() => setTarget({ program: null })}>
          Назначить тренера
        </Button>
      </div>

      {active.length === 0 ? (
        <EmptyState icon={UserCog} title="Тренер не назначен" description="Назначьте тренера, чтобы группа получила занятия." />
      ) : (
        <ul className="space-y-3">
          {active.map((program) => (
            <li key={program.id} className="card card-body flex flex-wrap items-start justify-between gap-3" data-testid="trainer-program">
              <div className="min-w-0 space-y-1">
                <p className="text-sm text-ink-secondary">Предмет: {program.subject?.name ?? 'без предмета'}</p>
                <p className="font-medium text-ink">
                  👨‍🏫{' '}
                  <Link to={`/app/trainers/${program.teacher.id}`} className="text-brand-700 hover:underline">
                    {program.teacher.name}
                  </Link>
                </p>
                <p className="text-xs text-ink-muted">
                  {program.assigned_by ? `Назначил: ${program.assigned_by} · ` : ''}Дата назначения: {formatDate(program.assigned_at)}
                </p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => setTarget({ program })}>
                Изменить тренера
              </Button>
            </li>
          ))}
        </ul>
      )}

      {target ? (
        <AssignTrainerModal overview={data} groupId={groupId} program={target.program} onClose={() => setTarget(null)} />
      ) : null}
    </section>
  )
}

function AssignTrainerModal({
  overview,
  groupId,
  program,
  onClose,
}: {
  overview: TrainerAssignmentOverview
  groupId: number
  program: TrainerAssignmentProgram | null
  onClose: () => void
}) {
  const { showToast } = useToast()
  const mutation = useAssignTrainer(groupId)
  const [subject, setSubject] = useState(program?.subject ? String(program.subject.id) : '')
  const [teacher, setTeacher] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  // Replacing: either the program chosen, or the subject's current trainer.
  const current =
    program ?? overview.programs.find((p) => p.is_active && p.subject && String(p.subject.id) === subject) ?? null
  const newTrainer = overview.trainers.find((t) => String(t.id) === teacher)

  function validate(): boolean {
    if (!program && !subject) {
      setError('Выберите предмет.')
      return false
    }
    if (!teacher) {
      setError('Выберите тренера.')
      return false
    }
    if (current && String(current.teacher.id) === teacher) {
      setError('Этот тренер уже назначен.')
      return false
    }
    setError(null)
    return true
  }

  async function save() {
    try {
      const result = await mutation.mutateAsync(
        current ? { teacher: Number(teacher), program: current.id } : { teacher: Number(teacher), subject: Number(subject) },
      )
      showToast(
        result.result?.previous_teacher
          ? `Тренер изменён: ${result.result.previous_teacher} → ${result.result.teacher}`
          : `Тренер назначен: ${result.result?.teacher ?? newTrainer?.name ?? ''}`,
        'success',
      )
      onClose()
    } catch (err) {
      setConfirming(false)
      setError(extractErrorMessage(err, 'Не удалось назначить тренера'))
    }
  }

  function handlePrimary() {
    if (!validate()) return
    if (current && !confirming) {
      setConfirming(true)
      return
    }
    void save()
  }

  return (
    <Modal isOpen onClose={onClose} title={confirming ? 'Изменить тренера?' : current ? 'Изменить тренера' : 'Назначить тренера'}>
      {confirming && current && newTrainer ? (
        <div className="space-y-2 text-sm" data-testid="confirm-change">
          <p>
            Группа: <strong>{overview.group.name}</strong>
            {current.subject ? ` · ${current.subject.name}` : ''}
          </p>
          <p>
            Сейчас: <strong>{current.teacher.name}</strong>
          </p>
          <p>
            Новый: <strong>{newTrainer.name}</strong>
          </p>
          <p className="text-ink-secondary">
            Будущие занятия перейдут новому тренеру, проведённые останутся за прежним. Изменить назначение?
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm">
            Группа: <strong>{overview.group.name}</strong>
          </p>
          {program ? (
            <p className="text-sm">
              Предмет: <strong>{program.subject?.name ?? 'без предмета'}</strong> · сейчас: {program.teacher.name}
            </p>
          ) : (
            <div>
              <label htmlFor="assign-subject" className="mb-1.5 block field-label">
                Предмет *
              </label>
              <Select
                id="assign-subject"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                placeholder="— Выберите предмет —"
                options={overview.subjects.map((s) => ({ value: String(s.id), label: s.name }))}
              />
              {current ? <p className="mt-1 text-xs text-ink-muted">Сейчас: {current.teacher.name}</p> : null}
            </div>
          )}
          <div>
            <label htmlFor="assign-teacher" className="mb-1.5 block field-label">
              Тренер *
            </label>
            <Select
              id="assign-teacher"
              value={teacher}
              onChange={(event) => setTeacher(event.target.value)}
              placeholder="— Выберите тренера —"
              options={overview.trainers.map((t) => ({
                value: String(t.id),
                label: t.subjects.length ? `${t.name} · ${t.subjects.join(', ')}` : t.name,
              }))}
            />
            <p className="mt-1 text-xs text-ink-muted">Только активные тренеры.</p>
          </div>
        </div>
      )}
      {error ? (
        <p className="mt-3 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={confirming ? () => setConfirming(false) : onClose} disabled={mutation.isPending}>
          Отмена
        </Button>
        <Button onClick={handlePrimary} isLoading={mutation.isPending}>
          {confirming ? 'Подтвердить' : current ? 'Изменить' : 'Назначить'}
        </Button>
      </div>
    </Modal>
  )
}
