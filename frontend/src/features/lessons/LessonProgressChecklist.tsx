import { CheckCircle2, Circle } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import type { Lesson } from '@/types/academy'

export interface LessonProgressChecklistProps {
  lesson: Lesson
  onMarkHomeworkNotRequired: () => void
  isMarkingHomeworkNotRequired?: boolean
}

/**
 * The compact "what's left before this lesson can be completed" checklist
 * for an in-progress lesson — every line reads a real backend field
 * (`attendance_completed`, `homework_added`, `homework_not_required`,
 * `can_complete`), never a client-side re-derivation of those rules.
 */
export function LessonProgressChecklist({
  lesson,
  onMarkHomeworkNotRequired,
  isMarkingHomeworkNotRequired = false,
}: LessonProgressChecklistProps) {
  const homeworkDone = lesson.homework_added || lesson.homework_not_required

  return (
    <div className="space-y-2 text-sm">
      <ChecklistLine ok text="Занятие начато" />
      <ChecklistLine ok={lesson.attendance_completed} text={lesson.attendance_completed ? 'Посещаемость отмечена' : 'Посещаемость не отмечена'} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ChecklistLine
          ok={homeworkDone}
          text={lesson.homework_added ? 'Домашнее задание добавлено' : lesson.homework_not_required ? 'ДЗ не требуется' : 'Домашнее задание не добавлено'}
        />
        {!homeworkDone ? (
          <Button
            variant="ghost"
            size="sm"
            isLoading={isMarkingHomeworkNotRequired}
            onClick={onMarkHomeworkNotRequired}
          >
            Отметить «ДЗ не требуется»
          </Button>
        ) : null}
      </div>
      <ChecklistLine ok={lesson.can_complete} text={lesson.can_complete ? 'Готово к завершению' : 'Ещё не готово к завершению'} />
    </div>
  )
}

function ChecklistLine({ ok, text }: { ok: boolean; text: string }) {
  const Icon = ok ? CheckCircle2 : Circle
  return (
    <p className={ok ? 'flex items-center gap-2 text-brand-700' : 'flex items-center gap-2 text-ink-secondary'}>
      <Icon className="size-4 shrink-0" aria-hidden />
      {text}
    </p>
  )
}
