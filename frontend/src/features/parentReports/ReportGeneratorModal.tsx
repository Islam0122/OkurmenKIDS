import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Eye, FileBarChart, Sparkles } from 'lucide-react'
import { isAxiosError } from 'axios'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useGroups } from '@/hooks/useGroups'
import { useGenerateParentReport, useParentReportPreview } from '@/hooks/useParentReports'
import type { ParentReportConfig, ParentReportDetail, ParentReportPreview, ReportPeriodKey } from '@/types/parentReports'
import { cn } from '@/utils/cn'
import { formatDateShort } from '@/utils/format'

import { ReportResult } from './ReportResult'
import {
  FORMAT_OPTIONS,
  LANGUAGE_OPTIONS,
  OPTION_LABELS,
  REPORT_TYPE_OPTIONS,
  STUDENT_STATUS_LABEL,
  STUDENT_STATUS_TONE,
  defaultConfig,
  fmtPercent,
  fmtScore,
  getReportPeriods,
} from './reportConfig'

interface ReportGeneratorModalProps {
  isOpen: boolean
  onClose: () => void
  groupId: number
}

export function ReportGeneratorModal({ isOpen, onClose, groupId }: ReportGeneratorModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Отчёт для родителей"
      icon={<FileBarChart size={18} className="shrink-0 text-brand-500" aria-hidden />}
      size="xl"
    >
      <GeneratorBody initialGroupId={groupId} />
    </Modal>
  )
}

/** Server validation message (e.g. «Дата начала не может быть позже…»), else a generic one. */
function errorMessage(error: unknown): string {
  if (isAxiosError(error) && error.response?.data && typeof error.response.data === 'object') {
    const data = error.response.data as Record<string, unknown>
    for (const value of Object.values(data)) {
      if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
      if (typeof value === 'string') return value
    }
  }
  return 'Не удалось сформировать отчёт. Попробуйте ещё раз.'
}

const GENERATION_STEPS = [
  'Считаем посещаемость и домашние задания…',
  'Сравниваем с прошлым периодом…',
  'Формируем рекомендации…',
  'Рисуем изображение отчёта…',
]

function GeneratorBody({ initialGroupId }: { initialGroupId: number }) {
  const [groupId, setGroupId] = useState(initialGroupId)
  const [config, setConfig] = useState<ParentReportConfig>(defaultConfig)
  const [previewConfig, setPreviewConfig] = useState<ParentReportConfig | null>(null)
  const [result, setResult] = useState<ParentReportDetail | null>(null)
  const periods = useMemo(() => getReportPeriods(), [])
  const { data: groupsData } = useGroups({})
  const generate = useGenerateParentReport()
  const preview = useParentReportPreview(previewConfig ? groupId : null, previewConfig)

  const isCustom = config.period === 'custom'
  const customInvalid = isCustom && (!config.start_date || !config.end_date || config.start_date > config.end_date)
  const selectedPeriod = periods.find((item) => item.key === config.period)

  function update(patch: Partial<ParentReportConfig>) {
    setConfig((current) => ({ ...current, ...patch }))
    setPreviewConfig(null)
  }

  function requestConfig(): ParentReportConfig {
    const { start_date, end_date, ...rest } = config
    return isCustom ? { ...rest, start_date, end_date } : rest
  }

  async function handleGenerate() {
    try {
      setResult(await generate.mutateAsync({ groupId, config: requestConfig() }))
    } catch {
      // Shown below from `generate.error`.
    }
  }

  if (result) {
    return (
      <div className="space-y-4">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<ArrowLeft className="size-4" aria-hidden />}
          onClick={() => {
            setResult(null)
            generate.reset()
          }}
        >
          Новый отчёт
        </Button>
        <ReportResult report={result} canEdit onRegenerated={setResult} />
      </div>
    )
  }

  if (generate.isPending) return <GenerationProgress wantsImage={config.output_format !== 'text'} />

  const groupOptions = (groupsData?.results ?? []).map((group) => ({ value: String(group.id), label: group.name }))
  if (!groupOptions.some((option) => option.value === String(groupId))) {
    groupOptions.unshift({ value: String(groupId), label: 'Текущая группа' })
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="field-label">Группа</span>
          <Select
            aria-label="Группа"
            value={String(groupId)}
            onChange={(event) => {
              setGroupId(Number(event.target.value))
              setPreviewConfig(null)
            }}
            options={groupOptions}
          />
        </label>
        <div>
          <span className="field-label">Язык</span>
          <SegmentedControl
            aria-label="Язык"
            value={config.language}
            onChange={(language) => update({ language })}
            options={LANGUAGE_OPTIONS}
          />
        </div>
      </div>

      <div>
        <span className="field-label">Период</span>
        <SegmentedControl<ReportPeriodKey>
          aria-label="Период"
          value={config.period}
          onChange={(period) => update({ period })}
          options={periods.map((item) => ({ value: item.key, label: item.label }))}
        />
        {isCustom ? (
          <div className="mt-2 grid gap-2 sm:max-w-md sm:grid-cols-2">
            <label className="block">
              <span className="field-label">С</span>
              <DatePicker aria-label="Дата начала" value={config.start_date ?? ''} onChange={(event) => update({ start_date: event.target.value })} />
            </label>
            <label className="block">
              <span className="field-label">По</span>
              <DatePicker aria-label="Дата окончания" value={config.end_date ?? ''} onChange={(event) => update({ end_date: event.target.value })} />
            </label>
            {config.start_date && config.end_date && config.start_date > config.end_date ? (
              <p className="text-xs text-danger sm:col-span-2">Дата начала не может быть позже даты окончания.</p>
            ) : null}
          </div>
        ) : selectedPeriod ? (
          <p className="mt-1 text-xs text-ink-muted">
            {formatDateShort(selectedPeriod.dateFrom)} — {formatDateShort(selectedPeriod.dateTo)} · сравнение с таким же
            прошлым периодом
          </p>
        ) : null}
      </div>

      <fieldset>
        <legend className="field-label">Тип отчёта</legend>
        <div role="radiogroup" aria-label="Тип отчёта" className="grid gap-2 sm:grid-cols-2">
          {REPORT_TYPE_OPTIONS.map((option) => {
            const active = option.value === config.report_type
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => update({ report_type: option.value })}
                className={cn(
                  'rounded-lg border px-3 py-2 text-left transition-colors',
                  active ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-border hover:border-brand-200 hover:bg-brand-50',
                )}
              >
                <span className="block text-sm font-medium text-ink">{option.label}</span>
                <span className="block text-xs text-ink-muted">{option.hint}</span>
              </button>
            )
          })}
        </div>
      </fieldset>

      <div>
        <span className="field-label">Формат</span>
        <SegmentedControl
          aria-label="Формат"
          value={config.output_format}
          onChange={(output_format) => update({ output_format })}
          options={FORMAT_OPTIONS}
        />
      </div>

      <div>
        <fieldset>
          <legend className="field-label">Что включить</legend>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {OPTION_LABELS.map((option) => (
              <label key={option.key} className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  className="size-4 accent-brand-500"
                  checked={config[option.key]}
                  onChange={(event) => update({ [option.key]: event.target.checked })}
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      {generate.isError ? (
        <div className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
          {errorMessage(generate.error)}
        </div>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
        <Button
          variant="secondary"
          leftIcon={<Eye className="size-4" aria-hidden />}
          disabled={customInvalid}
          onClick={() => setPreviewConfig(requestConfig())}
        >
          Предпросмотр данных
        </Button>
        <Button leftIcon={<Sparkles className="size-4" aria-hidden />} disabled={customInvalid} onClick={() => void handleGenerate()}>
          Сгенерировать отчёт
        </Button>
      </div>

      {previewConfig ? (
        preview.isPending ? (
          <LoadingState label="Считаем статистику…" />
        ) : preview.isError ? (
          <div className="space-y-2">
            <p className="text-sm text-danger" role="alert">{errorMessage(preview.error)}</p>
            <ErrorState onRetry={() => void preview.refetch()} />
          </div>
        ) : preview.data ? (
          <PreviewPanel preview={preview.data} config={previewConfig} />
        ) : null
      ) : null}
    </div>
  )
}

/** The request is one call; the steps show what the server is doing, without claiming a percentage. */
function GenerationProgress({ wantsImage }: { wantsImage: boolean }) {
  const steps = wantsImage ? GENERATION_STEPS : GENERATION_STEPS.slice(0, 3)
  const [step, setStep] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setStep((current) => Math.min(current + 1, steps.length - 1)), 1200)
    return () => window.clearInterval(timer)
  }, [steps.length])
  return (
    <div className="space-y-4 py-6" role="status" aria-live="polite">
      <p className="text-center text-sm font-medium text-ink">Формируем отчёт…</p>
      <div className="h-2 overflow-hidden rounded-full bg-surface-hover">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-brand-500" style={{ width: `${((step + 1) / steps.length) * 100}%` }} />
      </div>
      <ol className="space-y-1 text-sm">
        {steps.map((label, index) => (
          <li key={label} className={cn(index <= step ? 'text-ink' : 'text-ink-muted')}>
            {index < step ? '✓ ' : index === step ? '• ' : '  '}
            {label}
          </li>
        ))}
      </ol>
    </div>
  )
}

function PreviewPanel({ preview, config }: { preview: ParentReportPreview; config: ParentReportConfig }) {
  const { snapshot } = preview
  const stats = snapshot.group_stats
  const sections = preview.recommendations.group
  const text = config.report_type === 'students' ? Object.values(preview.student_texts)[0] ?? '' : preview.text
  return (
    <section aria-label="Предпросмотр" className="space-y-4 rounded-xl border border-border bg-surface-muted p-4">
      <p className="text-sm font-medium text-ink">
        Предпросмотр · {formatDateShort(snapshot.period.start)} — {formatDateShort(snapshot.period.end)}
      </p>
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Активные студенты" value={String(stats.active_students)} />
        <Stat label="Проведено занятий" value={`${stats.conducted_lessons} из ${stats.planned_lessons}`} />
        <Stat label="Посещаемость" value={fmtPercent(stats.attendance_rate)} />
        <Stat label="Домашние задания" value={fmtPercent(stats.homework_rate)} />
        <Stat label="Средний балл" value={fmtScore(stats.average_score)} />
        <Stat label="Тесты" value={fmtPercent(stats.test_average)} />
      </dl>
      {snapshot.students.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="data-table">
            <thead>
              <tr>
                <th>Студент</th><th>Посещаемость</th><th>ДЗ</th><th>Ср. балл</th><th>Тесты</th><th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.students.map((student) => (
                <tr key={student.id}>
                  <td className="font-medium">{student.name}</td>
                  <td>{fmtPercent(student.attendance_rate)}</td>
                  <td>{fmtPercent(student.homework_rate)}</td>
                  <td>{fmtScore(student.average_score)}</td>
                  <td>{fmtPercent(student.test_average)}</td>
                  <td><Badge tone={STUDENT_STATUS_TONE[student.status]}>{STUDENT_STATUS_LABEL[student.status]}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-ink-muted">В группе нет активных студентов за этот период.</p>
      )}
      {config.include_recommendations ? (
        <div className="grid gap-3 md:grid-cols-3">
          <Recommendations title="Наши сильные стороны" items={sections.strengths} className="bg-brand-50" />
          <Recommendations title="На что стоит обратить внимание" items={sections.attention} className="bg-warning-soft" />
          <Recommendations title="Рекомендации родителям" items={sections.parents} className="bg-info-soft" />
        </div>
      ) : null}
      {text ? (
        <div>
          <p className="field-label">Текст для WhatsApp{config.report_type === 'students' ? ' (пример — первый студент)' : ''}</p>
          <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-surface px-3 py-2 text-sm">
            {text}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="field-label">{label}</dt>
      <dd className="font-semibold text-ink tabular-nums">{value}</dd>
    </div>
  )
}

function Recommendations({ title, items, className }: { title: string; items: { key: string; text: string }[]; className: string }) {
  return (
    <div className={cn('rounded-lg p-3', className)}>
      <p className="mb-1 text-sm font-medium text-ink">{title}</p>
      <ul className="list-disc space-y-0.5 pl-4 text-sm text-ink-secondary">
        {items.map((item) => <li key={item.key}>{item.text}</li>)}
      </ul>
    </div>
  )
}
