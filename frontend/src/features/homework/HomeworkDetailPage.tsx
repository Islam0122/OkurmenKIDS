import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { HomeworkResultTable } from '@/components/academy/HomeworkResultTable'
import type { HomeworkResultPatch, HomeworkResultRow } from '@/components/academy/HomeworkResultTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { useToast } from '@/components/ui/Toast'
import { useHomeworkDetail, useHomeworkResultsRoster, useSaveHomeworkResults } from '@/hooks/useHomework'
import { extractErrorMessage } from '@/lib/apiError'
import type { BulkHomeworkResultItem, HomeworkResultStatus } from '@/types/homework'
import { formatDate } from '@/utils/format'

interface LocalEntry {
  status: HomeworkResultStatus
  score: number | null
  comment: string
}

export function HomeworkDetailPage() {
  const { id } = useParams<{ id: string }>()
  const homeworkId = Number(id)

  const { data: homework, isPending, isError, refetch } = useHomeworkDetail(homeworkId)
  const roster = useHomeworkResultsRoster(homeworkId)
  const saveMutation = useSaveHomeworkResults(homeworkId)
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
      await saveMutation.mutateAsync(items)
      showToast('Результаты сохранены', 'success')
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
      <PageHeader
        title={homework.title}
        description={`${homework.group_name} · ${formatDate(homework.lesson_date, false)}${homework.deadline ? ` · срок: ${formatDate(homework.deadline)}` : ''}`}
      />

      {homework.description ? (
        <div className="mb-6 rounded-xl border border-border bg-surface p-5">
          <p className="mb-2 text-sm font-medium text-ink-secondary">Описание</p>
          <p className="text-sm text-ink">{homework.description}</p>
        </div>
      ) : null}

      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm font-medium text-ink-secondary">Результаты студентов</p>
        <Link to={`/app/lessons/${homework.lesson}`} className="text-sm text-brand-700 hover:underline">
          Открыть занятие
        </Link>
      </div>

      {roster.isPending ? <LoadingState label="Загружаем список студентов…" /> : null}
      {roster.isError ? <ErrorState onRetry={() => void roster.refetch()} /> : null}

      {rows.length > 0 ? (
        <>
          <HomeworkResultTable rows={rows} onChange={handleChange} />
          <div className="sticky bottom-20 mt-4 flex justify-end lg:bottom-4">
            <Button onClick={() => void handleSave()} isLoading={saveMutation.isPending} size="lg">
              Сохранить результаты
            </Button>
          </div>
        </>
      ) : null}
    </div>
  )
}
