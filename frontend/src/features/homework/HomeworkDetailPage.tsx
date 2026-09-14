import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { HomeworkResultTable } from '@/components/academy/HomeworkResultTable'
import type { HomeworkResultPatch, HomeworkResultRow } from '@/components/academy/HomeworkResultTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useToast } from '@/components/ui/Toast'
import { useHomeworkDetail, useHomeworkResultsRoster, useSaveHomeworkResults } from '@/hooks/useHomework'
import { extractErrorMessage } from '@/lib/apiError'
import { useReturnLink } from '@/lib/returnTo'
import type { BulkHomeworkResultItem, HomeworkResultStatus } from '@/types/homework'
import { formatDate } from '@/utils/format'

/** No lesson to return to (opened straight from the homework list, not
 * from a Lesson Detail page) has nowhere sensible to go but that list. */
const HOMEWORK_LIST_PATH = '/app/homework'

interface LocalEntry {
  status: HomeworkResultStatus
  score: number | null
  comment: string
}

export function HomeworkDetailPage() {
  const { id } = useParams<{ id: string }>()
  const homeworkId = Number(id)
  const navigate = useNavigate()
  // Never trust the raw query value — `useReturnLink` only ever hands back
  // this same-app path or the safe fallback, so a crafted link can't send a
  // teacher who just saved results off to an external site.
  const returnLink = useReturnLink(HOMEWORK_LIST_PATH)

  const { data: homework, isPending, isError, refetch } = useHomeworkDetail(homeworkId)
  const roster = useHomeworkResultsRoster(homeworkId)
  const saveMutation = useSaveHomeworkResults(homeworkId, homework?.lesson)
  const { showToast } = useToast()

  const [localEntries, setLocalEntries] = useState<Record<number, LocalEntry>>({})

  useEffect(() => {
    if (!roster.data) return
    const initial: Record<number, LocalEntry> = {}
    for (const row of roster.data) {
      initial[row.student] = { status: row.status, score: row.score, comment: row.comment }
    }
    setLocalEntries(initial)
  }, [roster.data])

  if (isPending) return <LoadingState label="Загружаем задание…" />
  if (isError || !homework) return <ErrorState onRetry={() => void refetch()} />

  // Mirrors the backend's own enforcement (HomeworkSerializer.results_editable
  // / views._assert_homework_results_editable) — never re-derived from the
  // lesson status here, so the two can't drift apart.
  const isReadOnly = !homework.results_editable

  function handleChange(studentId: number, patch: HomeworkResultPatch) {
    setLocalEntries((prev) => ({
      ...prev,
      [studentId]: { ...prev[studentId], ...patch } as LocalEntry,
    }))
  }

  async function handleSave() {
    if (!roster.data) return
    const items: BulkHomeworkResultItem[] = roster.data.map((row) => {
      const entry = localEntries[row.student]
      return {
        student: row.student,
        status: entry?.status ?? row.status,
        score: entry?.score ?? null,
        comment: entry?.comment ?? '',
      }
    })
    try {
      // One bulk upsert either way (see services.homework_service on the
      // backend) — a first save creates every result, a later one updates
      // them, with no branching needed here for "create vs. update".
      await saveMutation.mutateAsync(items)
      showToast('Результаты успешно сохранены', 'success')
      // The mutation already invalidated this homework's and its lesson's
      // caches (see useSaveHomeworkResults), so landing back on the Lesson
      // Detail page refetches fresh — homework_added/results progress and
      // the completion checklist update on their own. `replace` drops the
      // just-submitted results form from history so Back doesn't return to
      // a now-stale page.
      navigate(returnLink.to, { replace: true })
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сохранить результаты'), 'error')
    }
  }

  const rows: HomeworkResultRow[] = (roster.data ?? []).map((row) => {
    const entry = localEntries[row.student]
    return {
      student: row.student,
      studentName: row.student_name,
      status: entry?.status ?? row.status,
      score: entry?.score ?? row.score,
      comment: entry?.comment ?? row.comment,
    }
  })

  return (
    <div>
      <BackLink to={returnLink.to}>{returnLink.hasOrigin ? 'Вернуться к занятию' : 'К списку домашних заданий'}</BackLink>

      <PageHeader
        title={homework.title}
        description={`${homework.group_name} · ${formatDate(homework.lesson_date, false)}${homework.deadline ? ` · срок: ${formatDate(homework.deadline)}` : ''}`}
        actions={isReadOnly ? <Badge tone="muted">Только просмотр</Badge> : undefined}
      />

      {isReadOnly ? (
        <div className="mb-6 rounded-lg bg-surface-muted px-4 py-3 text-sm text-ink-secondary">
          Занятие завершено — результаты домашнего задания больше нельзя редактировать.
        </div>
      ) : null}

      {homework.description ? (
        <div className="mb-6 rounded-xl border border-border bg-surface p-5">
          <p className="mb-2 text-sm font-medium text-ink-secondary">Описание</p>
          <p className="text-sm text-ink">{homework.description}</p>
        </div>
      ) : null}

      <p className="mb-4 text-sm font-medium text-ink-secondary">Результаты студентов</p>

      {roster.isPending ? <LoadingState label="Загружаем список студентов…" /> : null}
      {roster.isError ? <ErrorState onRetry={() => void roster.refetch()} /> : null}

      {rows.length > 0 ? (
        <>
          <HomeworkResultTable rows={rows} onChange={handleChange} readOnly={isReadOnly} />
          {!isReadOnly ? (
            <div className="sticky bottom-20 mt-4 flex justify-end lg:bottom-4">
              <Button onClick={() => void handleSave()} isLoading={saveMutation.isPending} size="lg">
                Сохранить результаты
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
