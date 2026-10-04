import { useState } from 'react'
import { Bot, Copy, MessageSquare, PenLine, RotateCcw, Save, TriangleAlert, UserRound, type LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useParentReport } from '@/hooks/useLessons'
import type { ParentLessonReport, ParentReportType } from '@/types/academy'
import { cn } from '@/utils/cn'
import { formatDate } from '@/utils/format'

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
 * «Мини-отчёт родителям»: pick the report author → preview → edit → copy. The trainer
 * pastes the copied text into whatever chat they use — nothing is sent from here.
 * Both automatic texts come from the backend, built from the lesson's real records;
 * the author choice and «Свой вариант» edits stay local to this dialog and never change
 * anything in the LMS. The report is fetched only while the dialog is open and is never
 * reused: each opening sends a new GET, so changes to attendance, homework or grades
 * made since the last opening are always in the preview.
 */
export function ParentReportModal({ lessonId, isOpen, onClose }: { lessonId: number; isOpen: boolean; onClose: () => void }) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Мини-отчёт родителям"
      icon={<MessageSquare size={18} className="shrink-0 text-brand-500" aria-hidden />}
      size="lg"
    >
      <ParentReportBody lessonId={lessonId} />
    </Modal>
  )
}

/** Mounted only while the dialog is open, so the query (and its cache entry) lives
 * exactly as long as one opening. */
function ParentReportBody({ lessonId }: { lessonId: number }) {
  const { data, isPending, isError, refetch } = useParentReport(lessonId)

  if (isPending) return <LoadingState label="Формируем отчёт…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />
  return <ReportEditor key={data.message} report={data} />
}

const AUTHORS: { value: ParentReportType; label: string; hint: string; icon: LucideIcon }[] = [
  { value: 'system', label: 'Система', hint: 'Автоматически сформированный отчёт', icon: Bot },
  { value: 'trainer', label: 'Тренер', hint: 'Отчёт от имени тренера', icon: UserRound },
  { value: 'custom', label: 'Свой вариант', hint: 'Можно изменить текст вручную', icon: PenLine },
]

function ReportEditor({ report }: { report: ParentLessonReport }) {
  const { showToast } = useToast()
  const [author, setAuthor] = useState<ParentReportType>('system')
  // «Свой вариант»: a copy of an automatic text, created on first use.
  const [customText, setCustomText] = useState<string | null>(null)
  const [isEditing, setEditing] = useState(false)
  const text = author === 'custom' ? (customText ?? report.messages.system) : report.messages[author]
  const isEmpty = !text.trim()

  function selectAuthor(next: ParentReportType) {
    if (next === 'custom') {
      if (customText === null) setCustomText(author === 'custom' ? report.messages.system : report.messages[author])
      setEditing(true)
    } else {
      setEditing(false)
    }
    setAuthor(next)
  }

  function startEditing() {
    // Editing an automatic text turns it into «Свой вариант», starting from what is on screen.
    if (author !== 'custom') setCustomText(text)
    setAuthor('custom')
    setEditing(true)
  }

  async function handleCopy() {
    try {
      await copyText(text)
      showToast('Отчёт скопирован', 'success')
    } catch {
      showToast('Не удалось скопировать — выделите текст вручную', 'error')
    }
  }

  return (
    <div className="space-y-4">
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium text-ink">Автор отчёта</legend>
        <div role="radiogroup" aria-label="Автор отчёта" className="grid gap-2 sm:grid-cols-2">
          {AUTHORS.map((option) => {
            const isActive = option.value === author
            const Icon = option.icon
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={isActive}
                onClick={() => selectAuthor(option.value)}
                className={cn(
                  'flex items-start gap-2 rounded-lg border px-3 py-2 text-left transition-colors',
                  // «Свой вариант» takes the full row under «Система» and «Тренер».
                  option.value === 'custom' && 'sm:col-span-2',
                  isActive
                    ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500'
                    : 'border-border bg-surface hover:border-brand-200 hover:bg-brand-50',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border-2',
                    isActive ? 'border-brand-500' : 'border-border',
                  )}
                >
                  {isActive ? <span className="size-2 rounded-full bg-brand-500" /> : null}
                </span>
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
                    <Icon size={18} className={cn('shrink-0', isActive ? 'text-brand-500' : 'text-ink-muted')} aria-hidden />
                    {option.label}
                  </span>
                  <span className="block text-xs text-ink-muted">{option.hint}</span>
                </span>
              </button>
            )
          })}
        </div>
      </fieldset>

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
      </p>

      {isEditing ? (
        <div className="space-y-1.5">
          <Textarea
            aria-label="Текст отчёта"
            value={text}
            onChange={(event) => setCustomText(event.target.value)}
            rows={16}
            className="text-sm leading-relaxed"
            autoFocus
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
            <span>Символов: {text.length}</span>
            {text !== report.messages.system ? (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<RotateCcw className="size-4" aria-hidden />}
                onClick={() => setCustomText(report.messages.system)}
              >
                Вернуть системный текст
              </Button>
            ) : null}
          </div>
          <p className="text-xs text-ink-muted">
            Меняется только текст сообщения — занятие, посещаемость, ДЗ и оценки остаются как есть.
          </p>
        </div>
      ) : (
        <div
          data-testid="parent-report-preview"
          className="max-h-[45dvh] overflow-y-auto whitespace-pre-wrap break-words rounded-2xl rounded-tl-sm border border-border bg-brand-50 px-4 py-3 text-sm leading-relaxed text-ink"
        >
          {text}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4 [&>*]:flex-1 sm:[&>*]:flex-none">
        {isEditing ? (
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Save className="size-4" aria-hidden />}
            onClick={() => setEditing(false)}
          >
            Сохранить
          </Button>
        ) : (
          <Button variant="secondary" size="sm" leftIcon={<PenLine size={16} aria-hidden />} onClick={startEditing}>
            Редактировать
          </Button>
        )}
        <Button size="sm" leftIcon={<Copy size={16} aria-hidden />} onClick={() => void handleCopy()} disabled={isEmpty}>
          Копировать
        </Button>
      </div>
    </div>
  )
}
