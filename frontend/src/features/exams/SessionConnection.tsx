import { useEffect, useState } from 'react'
import { Check, Copy, ExternalLink } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import type { ExamSession } from '@/types/exams'

const COPIED_MS = 2000

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall back below */
  }
  try {
    const field = document.createElement('textarea')
    field.value = text
    field.setAttribute('readonly', '')
    field.style.position = 'fixed'
    field.style.opacity = '0'
    document.body.appendChild(field)
    field.select()
    const ok = document.execCommand('copy')
    field.remove()
    return ok
  } catch {
    return false
  }
}

function CopyButton({ value, label, compact = false }: { value: string; label: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false)
  const { showToast } = useToast()
  useEffect(() => {
    if (!copied) return
    const id = window.setTimeout(() => setCopied(false), COPIED_MS)
    return () => window.clearTimeout(id)
  }, [copied])
  async function copy() {
    if (await writeClipboard(value)) setCopied(true)
    else showToast('Не удалось скопировать — выделите текст вручную', 'error')
  }
  const Icon = copied ? Check : Copy
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      onClick={() => void copy()}
      aria-label={copied ? 'Скопировано' : label}
      leftIcon={<Icon className={copied ? 'size-4 text-success' : 'size-4'} aria-hidden />}
      className="shrink-0"
    >
      {compact ? <span className="sr-only sm:not-sr-only">{copied ? 'Скопировано' : 'Копировать'}</span> : copied ? 'Скопировано' : 'Копировать'}
    </Button>
  )
}

/** «Данные для подключения»: the session code and the link students open —
 * both exactly as the backend returns them (key, join_url). */
export function SessionConnection({ session }: { session: ExamSession }) {
  const closed = session.phase === 'finished' || session.phase === 'cancelled'
  return (
    <section className="card card-body mb-6" aria-labelledby="session-connection-title">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="session-connection-title" className="section-title">Данные для подключения</h2>
        <p className="text-xs text-ink-muted">
          {closed ? 'Сессия закрыта — студенты больше не могут войти.' : 'Студент открывает ссылку (или вводит код) и выбирает себя из списка группы.'}
        </p>
      </div>

      <dl className="space-y-4">
        <div>
          <dt className="mb-1.5 text-sm font-medium text-ink-secondary">Код сессии</dt>
          <dd className="flex min-w-0 items-center justify-between gap-3 rounded-lg border border-border bg-surface-muted px-3 py-2">
            <span className="min-w-0 font-mono text-xl font-semibold tracking-[0.12em] text-ink [overflow-wrap:anywhere]">{session.key}</span>
            <CopyButton value={session.key} label="Копировать код сессии" compact />
          </dd>
        </div>

        {session.join_url ? (
          <div>
            <dt className="mb-1.5 text-sm font-medium text-ink-secondary">Ссылка на тест</dt>
            <dd className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface-muted px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
              <a
                href={session.join_url}
                target="_blank"
                rel="noopener noreferrer"
                title={session.join_url}
                className="min-w-0 font-mono text-sm text-brand-700 hover:underline [overflow-wrap:anywhere]"
              >
                {session.join_url}
              </a>
              <span className="flex shrink-0 gap-2">
                <CopyButton value={session.join_url} label="Копировать ссылку на тест" />
                <a
                  href={session.join_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-sm font-medium text-ink hover:bg-surface-hover"
                >
                  <ExternalLink className="size-4" aria-hidden />
                  Открыть
                </a>
              </span>
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  )
}
