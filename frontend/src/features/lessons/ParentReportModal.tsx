import { useState } from 'react'
import { Check, Copy, Pencil, RotateCcw, Send, TriangleAlert } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useParentReport } from '@/hooks/useLessons'
import type { ParentLessonReport } from '@/types/academy'
import { formatDate } from '@/utils/format'

/** Telegram's share screen with the text prefilled (there is no bot integration —
 * the trainer picks the parents' chat themselves). */
export function telegramShareUrl(text: string): string {
  return `https://t.me/share/url?url=${encodeURIComponent(text)}`
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  area.remove()
  if (!ok) throw new Error('copy failed')
}

/**
 * «Мини-отчёт родителям»: preview → edit → copy / send to Telegram.
 * The text is built on the backend from the lesson's real records; edits stay
 * local to this dialog (reopening it rebuilds the report).
 */
export function ParentReportModal({ lessonId, isOpen, onClose }: { lessonId: number; isOpen: boolean; onClose: () => void }) {
  const { data, isPending, isError, refetch } = useParentReport(lessonId, isOpen)

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Мини-отчёт родителям" size="lg">
      {isPending ? (
        <LoadingState label="Формируем отчёт…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : (
        <ReportEditor key={data.message} report={data} />
      )}
    </Modal>
  )
}

function ReportEditor({ report }: { report: ParentLessonReport }) {
  const { showToast } = useToast()
  const [text, setText] = useState(report.message)
  const [isEditing, setEditing] = useState(false)
  const [copied, setCopied] = useState(false)
  const isEdited = text !== report.message
  const isEmpty = !text.trim()

  async function handleCopy(silent = false) {
    try {
      await copyText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
      if (!silent) showToast('Текст скопирован', 'success')
    } catch {
      showToast('Не удалось скопировать — выделите текст вручную', 'error')
    }
  }

  return (
    <div className="space-y-4">
      {report.warnings.length > 0 ? (
        <div className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning" role="status">
          <p className="flex items-center gap-1.5 font-medium">
            <TriangleAlert className="size-4" aria-hidden />
            Проверьте перед отправкой
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
            {report.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs text-ink-muted">
        {report.group} · {formatDate(report.lesson_date)}
        {report.homework_checked
          ? ` · ДЗ проверено по занятию №${report.homework_checked.lesson_number} от ${formatDate(report.homework_checked.lesson_date)}`
          : ''}
      </p>

      {isEditing ? (
        <Textarea
          aria-label="Текст отчёта"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={16}
          className="text-sm leading-relaxed"
          autoFocus
        />
      ) : (
        <div
          data-testid="parent-report-preview"
          className="max-h-[45dvh] overflow-y-auto whitespace-pre-wrap break-words rounded-2xl rounded-tl-sm border border-border bg-brand-50 px-4 py-3 text-sm leading-relaxed text-ink"
        >
          {text}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={isEditing ? <Check className="size-4" aria-hidden /> : <Pencil className="size-4" aria-hidden />}
            onClick={() => setEditing((value) => !value)}
          >
            {isEditing ? 'Готово' : 'Редактировать'}
          </Button>
          {isEdited ? (
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<RotateCcw className="size-4" aria-hidden />}
              onClick={() => {
                setText(report.message)
                setEditing(false)
              }}
            >
              Сбросить правки
            </Button>
          ) : null}
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto [&>*]:flex-1 sm:[&>*]:flex-none">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
            onClick={() => void handleCopy()}
            disabled={isEmpty}
          >
            {copied ? 'Скопировано' : 'Копировать'}
          </Button>
          <a
            href={isEmpty ? undefined : telegramShareUrl(text)}
            target="_blank"
            rel="noreferrer"
            aria-disabled={isEmpty}
            onClick={(event) => {
              if (isEmpty) {
                event.preventDefault()
                return
              }
              // Also on the clipboard: if Telegram trims the prefilled text, it can be pasted.
              void handleCopy(true)
            }}
            className="inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg bg-brand-500 px-3 text-sm font-medium text-white hover:bg-brand-600 aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
          >
            <Send className="size-4" aria-hidden />
            Отправить в Telegram
          </a>
        </div>
      </div>
    </div>
  )
}
