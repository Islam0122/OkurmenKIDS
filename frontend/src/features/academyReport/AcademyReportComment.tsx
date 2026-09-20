import { useState } from 'react'
import { Pencil } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useUpdateAcademyReportComment } from '@/hooks/useAcademyReports'
import { extractErrorMessage } from '@/lib/apiError'
import type { AcademyMonthlyReport } from '@/types/academyReport'

/** Admin's own closing comment for the whole academy — a separate field
 * from a Teacher's own per-report comment (`MonthlyTeacherReport.comment`),
 * never mixed together (spec §15). */
export function AcademyReportComment({ report, canEdit }: { report: AcademyMonthlyReport; canEdit: boolean }) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(report.comment)
  const { showToast } = useToast()
  const mutation = useUpdateAcademyReportComment(report.id)

  function startEditing() {
    setDraft(report.comment)
    setIsEditing(true)
  }

  async function handleSave() {
    try {
      await mutation.mutateAsync(draft)
      setIsEditing(false)
      showToast('Комментарий сохранён', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сохранить комментарий'), 'error')
    }
  }

  if (isEditing) {
    return (
      <div className="space-y-3">
        <Textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Как прошёл месяц для академии?" autoFocus />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={() => setIsEditing(false)} disabled={mutation.isPending}>
            Отмена
          </Button>
          <Button size="sm" onClick={() => void handleSave()} isLoading={mutation.isPending}>
            Сохранить
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div>
      {report.comment ? (
        <p className="whitespace-pre-wrap text-sm text-ink">{report.comment}</p>
      ) : (
        <p className="text-sm text-ink-muted">Комментарий за этот месяц ещё не добавлен.</p>
      )}
      {canEdit ? (
        <Button variant="secondary" size="sm" className="mt-3" leftIcon={<Pencil className="size-3.5" aria-hidden />} onClick={startEditing}>
          {report.comment ? 'Редактировать комментарий' : 'Добавить комментарий'}
        </Button>
      ) : null}
    </div>
  )
}
