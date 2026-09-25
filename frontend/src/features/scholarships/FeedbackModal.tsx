import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useSaveFeedback } from '@/hooks/useScholarships'
import { extractErrorMessage } from '@/lib/apiError'
import { FEEDBACK_CRITERIA, type RequiredFeedbackItem, type TrainerFeedbackInput } from '@/types/scholarship'
import { cn } from '@/utils/cn'

const SCALE = [1, 2, 3, 4, 5]

interface FeedbackModalProps {
  periodId: number
  item: RequiredFeedbackItem | null
  readOnly: boolean
  onClose: () => void
}

function initialValues(item: RequiredFeedbackItem | null): Partial<TrainerFeedbackInput> {
  if (!item?.feedback) return { comment: '' }
  const { progress, participation, discipline, understanding, comment } = item.feedback
  return { progress, participation, discipline, understanding, comment }
}

/** 1–5 per criterion; nothing is pre-filled for a new assessment, so a
 * trainer can never submit a "default" score by accident. */
export function FeedbackModal({ periodId, item, readOnly, onClose }: FeedbackModalProps) {
  const [values, setValues] = useState<Partial<TrainerFeedbackInput>>(() => initialValues(item))
  const save = useSaveFeedback(periodId)
  const { showToast } = useToast()

  useEffect(() => setValues(initialValues(item)), [item])

  const isComplete = FEEDBACK_CRITERIA.every(({ key }) => typeof values[key] === 'number')

  async function handleSubmit() {
    if (!item || !isComplete) return
    try {
      await save.mutateAsync({ item, values: values as TrainerFeedbackInput })
      showToast('Оценка сохранена', 'success')
      onClose()
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось сохранить оценку'), 'error')
    }
  }

  return (
    <Modal isOpen={item !== null} onClose={onClose} title={item ? `${item.student_name} · ${item.subject_name}` : ''}>
      <div className="space-y-4">
        {FEEDBACK_CRITERIA.map(({ key, label }) => (
          <fieldset key={key}>
            <legend className="mb-1.5 text-sm font-medium text-ink">{label}</legend>
            <div className="flex gap-2" role="radiogroup" aria-label={label}>
              {SCALE.map((score) => (
                <button
                  key={score}
                  type="button"
                  role="radio"
                  aria-checked={values[key] === score}
                  disabled={readOnly}
                  onClick={() => setValues((prev) => ({ ...prev, [key]: score }))}
                  className={cn(
                    'size-10 rounded-lg border text-sm font-semibold transition-colors disabled:cursor-not-allowed',
                    values[key] === score
                      ? 'border-brand-500 bg-brand-500 text-white'
                      : 'border-border bg-surface text-ink hover:border-brand-200 hover:bg-brand-50',
                  )}
                >
                  {score}
                </button>
              ))}
            </div>
          </fieldset>
        ))}

        <div>
          <label htmlFor="feedback-comment" className="mb-1.5 block text-sm font-medium text-ink">
            Комментарий
          </label>
          <Textarea
            id="feedback-comment"
            rows={3}
            maxLength={2000}
            disabled={readOnly}
            value={values.comment ?? ''}
            onChange={(event) => setValues((prev) => ({ ...prev, comment: event.target.value }))}
          />
        </div>

        <p className="text-xs text-ink-muted">
          1 — очень слабо, 5 — отлично. Итоговая оценка = среднее по 4 критериям ÷ 5 × 100.
        </p>

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {readOnly ? 'Закрыть' : 'Отмена'}
          </Button>
          {readOnly ? null : (
            <Button onClick={() => void handleSubmit()} disabled={!isComplete} isLoading={save.isPending}>
              Сохранить
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
