import { useEffect, useMemo, useState } from 'react'
import { Copy, Download, FileArchive, ImageOff, RefreshCw, RotateCcw, Save, TriangleAlert } from 'lucide-react'

import { parentReportsApi } from '@/api/parentReports'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { useParentReportImage, useRegenerateParentReport, useSaveParentReportText } from '@/hooks/useParentReports'
import type { ParentReportDetail, ParentReportImage } from '@/types/parentReports'
import { copyText } from '@/utils/clipboard'
import { cn } from '@/utils/cn'
import { formatDateShort } from '@/utils/format'

import { STUDENT_STATUS_LABEL, STUDENT_STATUS_TONE, fmtPercent, fmtScore } from './reportConfig'

interface ReportResultProps {
  report: ParentReportDetail
  /** Admin / Trainer: «Перегенерировать». A Team Lead only reads. */
  canEdit: boolean
  /** Called with the new report after «Перегенерировать». */
  onRegenerated?: (report: ParentReportDetail) => void
}

/** A generated report: PNG preview + download, the editable WhatsApp text + copy. */
export function ReportResult({ report, canEdit, onRegenerated }: ReportResultProps) {
  const { showToast } = useToast()
  const regenerate = useRegenerateParentReport()
  const isStudents = report.report_type === 'students'
  const students = report.snapshot.students
  const [studentId, setStudentId] = useState<number | null>(isStudents ? (students[0]?.id ?? null) : null)
  const [pageIndex, setPageIndex] = useState(0)

  const images = report.images
  const visibleImages = isStudents ? images.filter((image) => image.student === studentId) : images
  const image: ParentReportImage | undefined = visibleImages[isStudents ? 0 : Math.min(pageIndex, visibleImages.length - 1)]

  async function handleRegenerate() {
    try {
      const fresh = await regenerate.mutateAsync(report.id)
      showToast('Отчёт пересчитан по актуальным данным', 'success')
      onRegenerated?.(fresh)
    } catch {
      showToast('Не удалось перегенерировать отчёт', 'error')
    }
  }

  async function handleDownload(imageId?: number) {
    try {
      await parentReportsApi.download(report.id, imageId)
    } catch {
      showToast('Не удалось скачать файл', 'error')
    }
  }

  return (
    <div className="space-y-5" data-testid="report-result">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">
            {report.group_name} · {formatDateShort(report.start_date)} — {formatDateShort(report.end_date)}
          </p>
          <p className="text-xs text-ink-muted">
            {report.report_type_display} · {report.language_display} · {report.output_format_display}
          </p>
        </div>
        {canEdit && report.group !== null ? (
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<RefreshCw className="size-4" aria-hidden />}
            isLoading={regenerate.isPending}
            onClick={() => void handleRegenerate()}
          >
            Перегенерировать
          </Button>
        ) : null}
      </div>

      {report.status === 'partial' ? (
        <div className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning" role="status">
          <p className="flex items-center gap-1.5 font-medium">
            <TriangleAlert className="size-4" aria-hidden /> Изображение не сформировано
          </p>
          <p className="mt-0.5 text-xs">{report.error} Текст и статистика сохранены — можно перегенерировать позже.</p>
        </div>
      ) : null}

      {isStudents && students.length > 0 ? (
        <Select
          aria-label="Студент"
          value={studentId === null ? '' : String(studentId)}
          onChange={(event) => setStudentId(Number(event.target.value))}
          options={students.map((student) => ({ value: String(student.id), label: student.name }))}
        />
      ) : null}

      {isStudents && studentId !== null ? <StudentSummary report={report} studentId={studentId} /> : null}

      {images.length > 0 ? (
        <section aria-label="Изображение отчёта" className="space-y-2">
          {!isStudents && visibleImages.length > 1 ? (
            <div className="flex flex-wrap gap-1" role="tablist" aria-label="Страницы">
              {visibleImages.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={index === pageIndex}
                  onClick={() => setPageIndex(index)}
                  className={cn(
                    'h-8 rounded-md px-3 text-sm font-medium',
                    index === pageIndex ? 'bg-brand-500 text-white' : 'bg-surface-hover text-ink-secondary hover:text-ink',
                  )}
                >
                  Стр. {item.page}
                </button>
              ))}
            </div>
          ) : null}
          {image ? <ImagePreview reportId={report.id} image={image} /> : <NoImage />}
          <div className="flex flex-wrap gap-2">
            {image ? (
              <Button size="sm" leftIcon={<Download className="size-4" aria-hidden />} onClick={() => void handleDownload(image.id)}>
                Скачать PNG
              </Button>
            ) : null}
            {images.length > 1 ? (
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<FileArchive className="size-4" aria-hidden />}
                onClick={() => void handleDownload()}
              >
                Скачать все ({images.length}, ZIP)
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}

      <TextEditor report={report} studentId={isStudents ? studentId : null} canEdit={canEdit} />
    </div>
  )
}

function NoImage() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-6 text-sm text-ink-muted">
      <ImageOff className="size-4" aria-hidden /> Изображения нет
    </div>
  )
}

function ImagePreview({ reportId, image }: { reportId: number; image: ParentReportImage }) {
  const { data: url, isPending, isError } = useParentReportImage(reportId, image.id)
  if (isPending) return <LoadingState label="Загружаем изображение…" />
  if (isError || !url) return <NoImage />
  return (
    <img
      src={url}
      alt={image.student_name ? `Отчёт: ${image.student_name}` : `Отчёт, страница ${image.page}`}
      width={image.width}
      height={image.height}
      className="h-auto w-full rounded-xl border border-border shadow-sm"
    />
  )
}

function StudentSummary({ report, studentId }: { report: ParentReportDetail; studentId: number }) {
  const student = report.snapshot.students.find((item) => item.id === studentId)
  if (!student) return null
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg bg-surface-muted px-3 py-2 text-sm">
      <Badge tone={STUDENT_STATUS_TONE[student.status]}>{STUDENT_STATUS_LABEL[student.status]}</Badge>
      <span>Посещаемость: <b>{fmtPercent(student.attendance_rate)}</b></span>
      <span>ДЗ: <b>{fmtPercent(student.homework_rate)}</b></span>
      <span>Средний балл: <b>{fmtScore(student.average_score)}</b></span>
      <span>Тесты: <b>{fmtPercent(student.test_average)}</b></span>
    </div>
  )
}

/** The WhatsApp message: editable before copying; «Сохранить» keeps the edit in the report history. */
function TextEditor({ report, studentId, canEdit }: { report: ParentReportDetail; studentId: number | null; canEdit: boolean }) {
  const { showToast } = useToast()
  const save = useSaveParentReportText(report.id)
  const key = studentId === null ? null : String(studentId)
  const generated = key === null ? report.text : (report.student_texts[key] ?? '')
  const stored = key === null ? report.final_text : (report.edited_student_texts[key] ?? generated)
  const [text, setText] = useState(stored)
  useEffect(() => setText(stored), [stored])

  const hasText = useMemo(() => Boolean(generated || stored), [generated, stored])
  if (!hasText) {
    return report.output_format === 'png' ? null : <p className="text-sm text-ink-muted">Текст не сформирован.</p>
  }

  async function handleCopy() {
    try {
      await copyText(text)
      showToast('Текст скопирован', 'success')
    } catch {
      showToast('Не удалось скопировать — выделите текст вручную', 'error')
    }
  }

  async function handleSave(reset = false) {
    try {
      await save.mutateAsync(reset ? { reset: true, student_id: studentId ?? undefined } : { text, student_id: studentId ?? undefined })
      showToast(reset ? 'Возвращён исходный текст' : 'Правка сохранена', 'success')
    } catch {
      showToast('Не удалось сохранить текст', 'error')
    }
  }

  return (
    <section aria-label="Текст для WhatsApp" className="space-y-2">
      <h3 className="text-sm font-medium text-ink">Текст для WhatsApp</h3>
      <Textarea
        aria-label="Текст для WhatsApp"
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={14}
        className="text-sm leading-relaxed"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-ink-muted">Символов: {text.length} · *жирный* — разметка WhatsApp</span>
        <div className="flex flex-wrap gap-2">
          {canEdit && text !== stored ? (
            <Button variant="secondary" size="sm" leftIcon={<Save className="size-4" aria-hidden />} isLoading={save.isPending} onClick={() => void handleSave()}>
              Сохранить правку
            </Button>
          ) : null}
          {canEdit && stored !== generated ? (
            <Button variant="ghost" size="sm" leftIcon={<RotateCcw className="size-4" aria-hidden />} onClick={() => void handleSave(true)}>
              Вернуть исходный
            </Button>
          ) : null}
          <Button size="sm" leftIcon={<Copy className="size-4" aria-hidden />} disabled={!text.trim()} onClick={() => void handleCopy()}>
            Скопировать текст
          </Button>
        </div>
      </div>
    </section>
  )
}
