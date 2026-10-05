import { useEffect, useState, type FormEvent } from 'react'

import { t } from '@/i18n'
import { NAME_MAX, cleanName, validateName, type NameError } from '@/lib/name'

import { Button } from '../Button'
import { Icon } from '../Icon'
import { Modal } from '../Modal'
import './NameModal.css'

/** «Атыңызды жазыңыз» — the only thing a student enters. No account. */
export function NameModal({ open, initialName, onSubmit, onClose, busy = false, serverError = null }: {
  open: boolean
  initialName: string
  busy?: boolean
  /** the backend's reason (it validates the name again) */
  serverError?: string | null
  onSubmit: (name: string) => void
  onClose: () => void
}) {
  const [name, setName] = useState(initialName)
  const [error, setError] = useState<NameError | null>(null)
  const [touched, setTouched] = useState(false)

  useEffect(() => { if (open) { setName(initialName); setError(null); setTouched(false) } }, [open, initialName])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const problem = validateName(name)
    setTouched(true)
    setError(problem)
    if (!problem) onSubmit(cleanName(name))
  }

  return (
    <Modal open={open} onClose={onClose} title={t.name.title} icon="person-badge" tone="primary" width={460}>
      <p className="modal__text">{t.name.subtitle}</p>
      <form className="name-form" onSubmit={submit} noValidate>
        <label className="field-label" htmlFor="student-name">{t.name.label}</label>
        <div className="field">
          <Icon name="person" />
          <input
            id="student-name"
            value={name}
            maxLength={NAME_MAX + 10}
            autoComplete="given-name"
            placeholder={t.name.placeholder}
            aria-invalid={touched && Boolean(error)}
            aria-describedby="student-name-help"
            onChange={(e) => { setName(e.target.value); if (touched) setError(validateName(e.target.value)) }}
          />
          <span className="field-count" aria-hidden="true">{cleanName(name).length}/{NAME_MAX}</span>
        </div>
        <div id="student-name-help">
          {touched && error
            ? <p className="field-error" role="alert"><Icon name="exclamation-circle" />{t.name.errors[error]}</p>
            : serverError
              ? <p className="field-error" role="alert"><Icon name="exclamation-circle" />{serverError}</p>
              : <p className="field-hint"><Icon name="shield-lock" />{t.name.privacy}</p>}
        </div>
        <div className="modal__actions">
          <Button variant="ghost" onClick={onClose}>{t.name.cancel}</Button>
          <Button type="submit" icon="play-fill" disabled={busy}>{t.name.submit}</Button>
        </div>
      </form>
    </Modal>
  )
}
