import { Button } from '@/components/Button'
import { Modal } from '@/components/Modal'
import type { TestModeConfig } from '@/components/TestScreen/modes'
import { t } from '@/i18n'
import { formatClock } from '@/lib/format'

/** «Finish?» — the same dialog for every mode: the mode's wording, the
 * unanswered warning where the mode asks for it, the numbers. */
export function ConfirmSubmitModal({ open, config, total, answered, secondsLeft, busy, onCancel, onConfirm }: {
  open: boolean
  config: TestModeConfig
  total: number
  answered: number
  secondsLeft: number | null
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { text } = config
  const unanswered = total - answered
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={text.finishTitle}
      icon="flag"
      tone="test"
      actions={<>
        <Button variant="outline" onClick={onCancel}>{text.keepGoing}</Button>
        <Button variant="test" icon="flag-fill" disabled={busy} onClick={onConfirm}>{text.finish}</Button>
      </>}
    >
      <p className="modal__text">{text.finishText}</p>
      {config.unansweredWarn && unanswered > 0 ? (
        <p className="finish-warn"><strong>{config.unansweredWarn(unanswered)}</strong></p>
      ) : null}
      <dl className="finish-stats">
        <div><dt>{t.training.total}</dt><dd>{total}</dd></div>
        <div><dt>{t.training.answered}</dt><dd>{answered}</dd></div>
        <div><dt>{t.training.unanswered}</dt><dd>{unanswered}</dd></div>
        <div><dt>{t.training.timeLeft}</dt><dd>{secondsLeft === null ? '—' : formatClock(secondsLeft)}</dd></div>
      </dl>
    </Modal>
  )
}
