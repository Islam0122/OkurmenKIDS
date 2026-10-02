import { ClipboardCheck } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import type { LessonHomeworkToCheck } from '@/types/academy'

export interface HomeworkToCheckCardProps {
  homework: LessonHomeworkToCheck
  onCheck: (homeworkId: number) => void
}

/**
 * The homework the trainer checks during an open lesson — the backend picks
 * it (LessonSerializer.homework_to_check: set in the previous, completed
 * lesson of the same program), so the page just shows the assignment and
 * the way into the existing grading page.
 */
export function HomeworkToCheckCard({ homework, onCheck }: HomeworkToCheckCardProps) {
  const { results_total: total, checked, pending } = homework.results_summary
  return (
    <div className="card card-body" data-testid="homework-to-check-card">
      <h2 className="section-title mb-3">📝 Домашнее задание</h2>
      <p className="font-medium text-ink">{homework.title}</p>
      {homework.description ? <p className="mt-1 whitespace-pre-line text-sm text-ink-secondary">{homework.description}</p> : null}
      {total > 0 ? (
        <p className="mt-2 text-sm text-ink-secondary">
          {total} результатов · проверено {checked} · ожидает {pending}
        </p>
      ) : null}
      {homework.can_check ? (
        <div className="pt-3">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<ClipboardCheck className="size-4" aria-hidden />}
            onClick={() => onCheck(homework.id)}
          >
            Проверить ДЗ
          </Button>
        </div>
      ) : null}
    </div>
  )
}
