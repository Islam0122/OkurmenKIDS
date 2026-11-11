import { useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, CheckCircle2, Copy, Download, FileSpreadsheet, History, Loader2, RotateCcw, Upload, XCircle,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { Tabs } from '@/components/ui/Tabs'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { useSiteInvalidate, useSiteMeta } from './api'
import { CHUNK, importApi, KIND_LABEL, KINDS, MAX_FILE_BYTES } from './importApi'
import type { Batch, BatchSummary, ImportKind, ImportRow, RowResult } from './importApi'

type Step = 'upload' | 'preview' | 'validation' | 'import'
const STEPS: { key: Step; label: string }[] = [
  { key: 'upload', label: 'Файл' },
  { key: 'preview', label: 'Просмотр' },
  { key: 'validation', label: 'Проверка' },
  { key: 'import', label: 'Импорт' },
]
const EDIT_PATH: Record<ImportKind, string> = { events: '/marketing/site/events', achievements: '/marketing/site/achievements', news: '/marketing/site/news' }
const RESULT_LABEL: Record<RowResult['result'], string> = { created: 'Создано', updated: 'Обновлено', skipped: 'Пропущено', failed: 'Ошибка' }
const RESULT_TONE = { created: 'success', updated: 'info', skipped: 'muted', failed: 'danger' } as const

const formatSize = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ`)
const formatDate = (iso: string) => {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU', iso.length === 10 ? { dateStyle: 'medium' } : { dateStyle: 'medium', timeStyle: 'short' })
}

/** «Массовое заполнение контента»: one Excel / CSV file → events, achievements, news as drafts. */
export function ContentImportPage() {
  const meta = useSiteMeta()
  const [tab, setTab] = useState<'import' | 'history'>('import')
  if (meta.isPending) return <LoadingState />
  if (meta.data && !meta.data.permissions.can_import) {
    return (
      <>
        <PageHeader title="Массовое заполнение контента" />
        <EmptyState title="Нет доступа" description="Массовый импорт доступен администратору и директору." />
      </>
    )
  }
  return (
    <>
      <PageHeader
        title="Массовое заполнение контента"
        description="Мероприятия, достижения и новости из одного файла Excel или CSV. Все записи импортируются неопубликованными — публикация только после проверки."
      />
      <div className="mb-5">
        <Tabs aria-label="Разделы импорта" value={tab} onChange={setTab} items={[{ key: 'import', label: 'Импорт' }, { key: 'history', label: 'История' }]} />
      </div>
      {tab === 'import' ? <ImportWizard /> : <ImportHistory />}
    </>
  )
}

function Stepper({ step }: { step: Step }) {
  const index = STEPS.findIndex((s) => s.key === step)
  return (
    <ol className="mb-5 grid grid-cols-4 gap-2" aria-label="Шаги импорта">
      {STEPS.map((s, i) => (
        <li key={s.key} aria-current={i === index ? 'step' : undefined}
          className={cn('min-w-0 rounded-lg border px-2 py-2 text-center text-xs font-medium sm:px-3 sm:text-sm',
            i === index ? 'border-brand-300 bg-brand-50 text-brand-700' : i < index ? 'border-border bg-surface text-ink-secondary' : 'border-border bg-surface text-ink-muted')}>
          <span className="mr-1 tabular-nums">{i + 1}.</span><span className="truncate">{s.label}</span>
        </li>
      ))}
    </ol>
  )
}

function ImportWizard() {
  const [step, setStep] = useState<Step>('upload')
  const [batch, setBatch] = useState<Batch | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [updates, setUpdates] = useState<Set<string>>(new Set())

  const reset = () => {
    setBatch(null)
    setSelected(new Set())
    setUpdates(new Set())
    setStep('upload')
  }
  const loaded = (b: Batch) => {
    setBatch(b)
    // Valid rows that are not duplicates are selected by default.
    setSelected(new Set(b.rows.filter((r) => r.valid).map((r) => r.key)))
    setUpdates(new Set())
    setStep('preview')
  }

  return (
    <>
      <Stepper step={step} />
      {step === 'upload' || !batch ? <UploadStep onLoaded={loaded} /> : null}
      {step === 'preview' && batch ? (
        <PreviewStep batch={batch} selected={selected} setSelected={setSelected} onBack={reset} onNext={() => setStep('validation')} />
      ) : null}
      {step === 'validation' && batch ? (
        <ValidationStep batch={batch} selected={selected} updates={updates} setUpdates={setUpdates}
          onBack={() => setStep('preview')} onNext={() => setStep('import')} />
      ) : null}
      {step === 'import' && batch ? (
        <ImportStep batch={batch} selected={selected} updates={updates} onBack={() => setStep('validation')} onFinished={setBatch} onReset={reset} />
      ) : null}
    </>
  )
}

// ---------------------------------------------------------------------------
// 1. Upload
// ---------------------------------------------------------------------------

function UploadStep({ onLoaded }: { onLoaded: (b: Batch) => void }) {
  const { showToast } = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [csvType, setCsvType] = useState<ImportKind | ''>('')
  const [sheets, setSheets] = useState<Set<ImportKind>>(new Set(KINDS))
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const isCsv = file?.name.toLowerCase().endsWith('.csv') ?? false

  const pick = (f: File | undefined) => {
    setError('')
    if (!f) return
    const name = f.name.toLowerCase()
    if (!name.endsWith('.xlsx') && !name.endsWith('.csv')) return setError('Поддерживаются только файлы .xlsx и .csv.')
    if (f.size > MAX_FILE_BYTES) return setError(`Файл больше ${MAX_FILE_BYTES / 1024 / 1024} МБ — разделите его.`)
    if (!f.size) return setError('Файл пустой.')
    setFile(f)
    const guess = KINDS.find((k) => name.includes(k))
    setCsvType(guess ?? '')
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files[0])
  }
  const submit = async () => {
    if (!file) return
    if (isCsv && !csvType) return setError('Выберите, что содержит CSV-файл.')
    if (!isCsv && !sheets.size) return setError('Выберите хотя бы один лист.')
    setBusy(true)
    setError('')
    try {
      onLoaded(await importApi.preview(file, isCsv ? { type: csvType as ImportKind } : { types: sheets.size === KINDS.length ? undefined : [...sheets] }))
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const template = (format: 'xlsx' | 'csv', type?: ImportKind) =>
    importApi.downloadTemplate(format, type).catch((err) => showToast(extractErrorMessage(err), 'error'))

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <Card title="Загрузите файл">
        <div
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn('flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors',
            dragging ? 'border-brand-400 bg-brand-50' : 'border-border hover:border-brand-300 hover:bg-surface-hover')}
        >
          <Upload className="size-8 text-brand-500" aria-hidden />
          <p className="font-medium text-ink">Перетащите файл сюда или нажмите, чтобы выбрать</p>
          <p className="text-sm text-ink-muted">.xlsx (листы Events, Achievements, News) или .csv · до {MAX_FILE_BYTES / 1024 / 1024} МБ</p>
          <input ref={input} type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
        </div>

        {file ? (
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-border bg-surface-muted px-3 py-2.5">
            <FileSpreadsheet className="size-5 shrink-0 text-brand-600" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{file.name}</p>
              <p className="text-xs text-ink-muted">{formatSize(file.size)}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setFile(null)}>Убрать</Button>
          </div>
        ) : null}

        {file && isCsv ? (
          <fieldset className="mt-4">
            <legend className="mb-2 text-sm font-medium text-ink">Что в CSV-файле?</legend>
            <div className="flex flex-wrap gap-2">
              {KINDS.map((k) => (
                <label key={k} className={cn('flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm', csvType === k ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-border')}>
                  <input type="radio" name="csv-type" value={k} checked={csvType === k} onChange={() => setCsvType(k)} className="accent-brand-500" />
                  {KIND_LABEL[k]}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}
        {file && !isCsv ? (
          <fieldset className="mt-4">
            <legend className="mb-2 text-sm font-medium text-ink">Какие листы импортировать</legend>
            <div className="flex flex-wrap gap-2">
              {KINDS.map((k) => (
                <label key={k} className={cn('flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm', sheets.has(k) ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-border')}>
                  <input type="checkbox" checked={sheets.has(k)} className="accent-brand-500"
                    onChange={() => setSheets((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n })} />
                  {KIND_LABEL[k]}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}

        {error ? <p role="alert" className="mt-4 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p> : null}
        <div className="mt-5 flex justify-end">
          <Button onClick={submit} disabled={!file} isLoading={busy}>Проверить файл</Button>
        </div>
      </Card>

      <Card title="Шаблоны" description="Только заголовки колонок и инструкция README — без примеров, которые можно случайно импортировать.">
        <div className="space-y-2">
          <Button variant="secondary" className="w-full justify-start" leftIcon={<Download className="size-4" />} onClick={() => template('xlsx')}>
            Excel: все листы
          </Button>
          {KINDS.map((k) => (
            <Button key={k} variant="ghost" className="w-full justify-start" leftIcon={<Download className="size-4" />} onClick={() => template('csv', k)}>
              CSV: {KIND_LABEL[k].toLowerCase()}
            </Button>
          ))}
        </div>
        <ul className="mt-4 list-disc space-y-1.5 pl-5 text-xs text-ink-secondary">
          <li>Обязательно: заголовок на русском, категория и дата.</li>
          <li>Переводы KG / EN — по желанию; без них сайт покажет русский текст.</li>
          <li>Не придумывайте даты, победителей и места — оставьте пусто и опишите в «verification_note».</li>
          <li>Изображения добавляются вручную в редакторе после импорта.</li>
        </ul>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 2. Preview
// ---------------------------------------------------------------------------

function ValidationBadge({ row }: { row: ImportRow }) {
  if (row.errors.length) return <Badge tone="danger"><XCircle className="size-3.5" aria-hidden />Ошибка</Badge>
  if (row.duplicate) return <Badge tone="info"><Copy className="size-3.5" aria-hidden />Уже есть</Badge>
  if (row.warnings.length) return <Badge tone="warning"><AlertTriangle className="size-3.5" aria-hidden />{row.warnings.length} предупр.</Badge>
  return <Badge tone="success"><CheckCircle2 className="size-3.5" aria-hidden />Готово</Badge>
}

function Languages({ row }: { row: ImportRow }) {
  return (
    <span className="inline-flex gap-1" aria-label="Языки">
      {(['ru', 'ky', 'en'] as const).map((lang) => (
        <span key={lang} title={row.languages[lang] ? 'Есть' : 'Нет перевода'}
          className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', row.languages[lang] ? 'bg-brand-50 text-brand-700' : 'bg-surface-hover text-ink-muted line-through')}>
          {lang === 'ky' ? 'KG' : lang.toUpperCase()}
        </span>
      ))}
    </span>
  )
}

function PreviewStep({ batch, selected, setSelected, onBack, onNext }: {
  batch: Batch; selected: Set<string>; setSelected: (s: Set<string>) => void; onBack: () => void; onNext: () => void
}) {
  const [filter, setFilter] = useState<ImportKind | 'all' | 'errors'>('all')
  const kinds = KINDS.filter((k) => batch.sheets[k] !== undefined)
  const rows = batch.rows.filter((r) => (filter === 'all' ? true : filter === 'errors' ? !r.valid : r.kind === filter))
  const selectable = rows.filter((r) => r.valid)
  const allOn = selectable.length > 0 && selectable.every((r) => selected.has(r.key))
  const toggle = (keys: string[], on: boolean) => {
    const next = new Set(selected)
    keys.forEach((k) => (on ? next.add(k) : next.delete(k)))
    setSelected(next)
  }
  const chips: { value: typeof filter; label: string; count: number }[] = [
    { value: 'all', label: 'Все', count: batch.rows.length },
    ...kinds.map((k) => ({ value: k, label: KIND_LABEL[k], count: batch.rows.filter((r) => r.kind === k).length })),
    { value: 'errors', label: 'С ошибками', count: batch.error_rows },
  ]

  return (
    <Card padding="none">
      <div className="card-body flex flex-col gap-3 border-b border-border sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{batch.file_name}</p>
          <p className="text-sm text-ink-secondary">
            {batch.total_rows} строк · выбрано {selected.size} · с ошибками {batch.error_rows}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Фильтр строк">
          {chips.map((c) => (
            <button key={c.value} type="button" onClick={() => setFilter(c.value)} aria-pressed={filter === c.value}
              className={cn('rounded-full border px-3 py-1 text-sm', filter === c.value ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-border text-ink-secondary hover:bg-surface-hover')}>
              {c.label} <span className="tabular-nums text-ink-muted">{c.count}</span>
            </button>
          ))}
        </div>
      </div>

      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] text-sm">
            <thead className="bg-surface-muted text-left text-xs text-ink-muted uppercase">
              <tr>
                <th className="w-10 px-4 py-2.5">
                  <input type="checkbox" aria-label="Выбрать все" checked={allOn} disabled={!selectable.length} className="accent-brand-500"
                    onChange={() => toggle(selectable.map((r) => r.key), !allOn)} />
                </th>
                <th className="px-2 py-2.5">Стр.</th>
                <th className="px-2 py-2.5">Название</th>
                <th className="px-2 py-2.5">Тип</th>
                <th className="px-2 py-2.5">Категория</th>
                <th className="px-2 py-2.5">Дата</th>
                <th className="px-2 py-2.5">Языки</th>
                <th className="px-2 py-2.5">Статус</th>
                <th className="px-4 py-2.5">Проверка</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((r) => (
                <tr key={r.key} className={cn(!r.valid && 'bg-danger-soft/40')}>
                  <td className="px-4 py-2.5">
                    <input type="checkbox" aria-label={`Строка ${r.row}`} checked={selected.has(r.key)} disabled={!r.valid} className="accent-brand-500"
                      onChange={() => toggle([r.key], !selected.has(r.key))} />
                  </td>
                  <td className="px-2 py-2.5 tabular-nums text-ink-muted">{r.row}</td>
                  <td className="max-w-[18rem] px-2 py-2.5">
                    <p className="line-clamp-2 font-medium text-ink">{r.title || <span className="text-ink-muted">без названия</span>}</p>
                    {r.errors[0] ? <p className="mt-0.5 line-clamp-1 text-xs text-danger">{r.errors[0].message}</p> : null}
                  </td>
                  <td className="px-2 py-2.5 whitespace-nowrap">{KIND_LABEL[r.kind]}</td>
                  <td className="px-2 py-2.5">{r.category || <span className="text-danger">{r.category_raw || '—'}</span>}</td>
                  <td className="px-2 py-2.5 whitespace-nowrap">{formatDate(r.date)}</td>
                  <td className="px-2 py-2.5"><Languages row={r} /></td>
                  <td className="px-2 py-2.5 whitespace-nowrap">{r.status === 'review' ? 'На согласовании' : r.status === 'archived' ? 'В архиве' : 'Черновик'}</td>
                  <td className="px-4 py-2.5"><ValidationBadge row={r} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState className="py-10" title="Нет строк" description={batch.total_rows ? 'В этом фильтре строк нет.' : 'Листы пустые — заполните шаблон и загрузите снова.'} />
      )}

      <div className="card-body flex flex-col-reverse gap-2 border-t border-border sm:flex-row sm:justify-between">
        <Button variant="ghost" leftIcon={<RotateCcw className="size-4" />} onClick={onBack}>Другой файл</Button>
        <Button onClick={onNext} disabled={!selected.size}>Проверка выбранных ({selected.size})</Button>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// 3. Validation
// ---------------------------------------------------------------------------

function ValidationStep({ batch, selected, updates, setUpdates, onBack, onNext }: {
  batch: Batch; selected: Set<string>; updates: Set<string>; setUpdates: (s: Set<string>) => void; onBack: () => void; onNext: () => void
}) {
  const chosen = batch.rows.filter((r) => selected.has(r.key))
  const invalid = batch.rows.filter((r) => !r.valid)
  const duplicates = chosen.filter((r) => r.duplicate)
  const withWarnings = chosen.filter((r) => r.warnings.length && !r.duplicate)
  const fresh = chosen.filter((r) => !r.duplicate)
  const setUpdate = (key: string, on: boolean) => {
    const next = new Set(updates)
    if (on) next.add(key)
    else next.delete(key)
    setUpdates(next)
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Summary label="Будут созданы" value={fresh.length} tone="success" />
        <Summary label="Уже существуют" value={duplicates.length} hint={`обновить: ${updates.size}`} tone="info" />
        <Summary label="С предупреждениями" value={withWarnings.length} tone="warning" />
        <Summary label="Не импортируются (ошибки)" value={invalid.length} tone="danger" />
      </div>

      {duplicates.length ? (
        <Card title="Существующие записи" description="По умолчанию пропускаются. Обновление меняет текст существующей записи и требует подтверждения на следующем шаге; опубликованные записи импорт не меняет.">
          <ul className="divide-y divide-border">
            {duplicates.map((r) => (
              <li key={r.key} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{r.title}</p>
                  <p className="text-xs text-ink-muted">{KIND_LABEL[r.kind]} · строка {r.row} · сейчас: «{r.duplicate!.title}», {r.duplicate!.status_label}</p>
                </div>
                <div className="flex shrink-0 gap-1.5" role="radiogroup" aria-label={`Строка ${r.row}`}>
                  <ChoiceButton active={!updates.has(r.key)} onClick={() => setUpdate(r.key, false)}>Пропустить</ChoiceButton>
                  <ChoiceButton active={updates.has(r.key)} disabled={!r.duplicate!.updatable} onClick={() => setUpdate(r.key, true)}
                    title={r.duplicate!.updatable ? undefined : 'Запись опубликована — правьте её в редакторе'}>Обновить</ChoiceButton>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {invalid.length ? (
        <Card title="Ошибки — эти строки не будут импортированы" description="Исправьте файл и загрузите его снова, или продолжайте без этих строк.">
          <MessageList rows={invalid} kind="errors" />
        </Card>
      ) : null}

      {withWarnings.length ? (
        <Card title="Предупреждения" description="Строки будут импортированы. Проверьте их перед публикацией.">
          <MessageList rows={withWarnings} kind="warnings" />
        </Card>
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <Button variant="ghost" onClick={onBack}>Назад к списку</Button>
        <Button onClick={onNext} disabled={!chosen.length}>Перейти к импорту</Button>
      </div>
    </div>
  )
}

function Summary({ label, value, hint, tone }: { label: string; value: number; hint?: string; tone: 'success' | 'info' | 'warning' | 'danger' }) {
  const color = { success: 'text-brand-700', info: 'text-info', warning: 'text-warning', danger: 'text-danger' }[tone]
  return (
    <div className="card card-body min-w-0">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', color)}>{value}</p>
      {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

function ChoiceButton({ active, disabled, onClick, title, children }: { active: boolean; disabled?: boolean; onClick: () => void; title?: string; children: string }) {
  return (
    <button type="button" role="radio" aria-checked={active} disabled={disabled} onClick={onClick} title={title}
      className={cn('rounded-lg border px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50',
        active ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-border text-ink-secondary hover:bg-surface-hover')}>
      {children}
    </button>
  )
}

function MessageList({ rows, kind }: { rows: ImportRow[]; kind: 'errors' | 'warnings' }) {
  const [all, setAll] = useState(false)
  const shown = all ? rows : rows.slice(0, 15)
  return (
    <>
      <ul className="divide-y divide-border">
        {shown.map((r) => (
          <li key={r.key} className="py-2.5">
            <p className="text-sm font-medium text-ink">
              <span className="text-ink-muted">{KIND_LABEL[r.kind]}, строка {r.row}:</span> {r.title || 'без названия'}
            </p>
            <ul className={cn('mt-1 list-disc space-y-0.5 pl-5 text-sm', kind === 'errors' ? 'text-danger' : 'text-ink-secondary')}>
              {r[kind].map((m, i) => <li key={i}>{m.message}</li>)}
            </ul>
          </li>
        ))}
      </ul>
      {rows.length > shown.length ? <Button variant="ghost" size="sm" className="mt-2" onClick={() => setAll(true)}>Показать все ({rows.length})</Button> : null}
    </>
  )
}

// ---------------------------------------------------------------------------
// 4. Import
// ---------------------------------------------------------------------------

function ImportStep({ batch, selected, updates, onBack, onFinished, onReset }: {
  batch: Batch; selected: Set<string>; updates: Set<string>; onBack: () => void; onFinished: (b: Batch) => void; onReset: () => void
}) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const queryClient = useQueryClient()
  const [confirmed, setConfirmed] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [result, setResult] = useState<Batch | null>(batch.finished_at ? batch : null)
  const [error, setError] = useState('')
  const keys = useMemo(() => batch.rows.filter((r) => selected.has(r.key) && r.valid).map((r) => r.key), [batch, selected])
  const updateKeys = keys.filter((k) => updates.has(k))

  const run = async () => {
    setError('')
    setProgress({ done: 0, total: keys.length })
    let last = batch
    try {
      for (let i = 0; i < keys.length; i += CHUNK) {
        const chunk = keys.slice(i, i + CHUNK)
        last = await importApi.commit(batch.id, {
          rows: chunk,
          update: chunk.filter((k) => updates.has(k)),
          confirm_update: updateKeys.length > 0 && confirmed,
          finalize: i + CHUNK >= keys.length,
        })
        setProgress({ done: Math.min(i + CHUNK, keys.length), total: keys.length })
      }
      setResult(last)
      onFinished(last)
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['site-import'] })
      showToast(`Импорт завершён: создано ${last.created_count}, обновлено ${last.updated_count}`, 'success')
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setProgress(null)
    }
  }

  if (result) return <ImportResults batch={result} onReset={onReset} />

  const running = progress !== null
  const pct = progress ? Math.round((progress.done / Math.max(progress.total, 1)) * 100) : 0
  return (
    <Card title="Импорт">
      <ul className="space-y-1.5 text-sm text-ink-secondary">
        <li>Будет обработано строк: <b className="text-ink">{keys.length}</b>{updateKeys.length ? <> (обновление существующих: <b className="text-ink">{updateKeys.length}</b>)</> : null}.</li>
        <li>Новые записи создаются черновиками (или «На согласовании», если так указано в файле) и <b className="text-ink">не появятся на сайте</b> до публикации.</li>
        <li>Существующие записи без выбора «Обновить» пропускаются. Каждая запись сохраняется отдельно: ошибка в одной не отменяет остальные.</li>
      </ul>
      {updateKeys.length ? (
        <label className="mt-4 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2.5 text-sm text-ink">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 accent-brand-500" />
          <span>Я подтверждаю обновление {updateKeys.length} существующих записей данными из файла.</span>
        </label>
      ) : null}
      {running ? (
        <div className="mt-5" role="status" aria-live="polite">
          <div className="mb-1 flex justify-between text-sm text-ink-secondary">
            <span className="inline-flex items-center gap-1.5"><Loader2 className="size-4 animate-spin" aria-hidden />Импортируется…</span>
            <span className="tabular-nums">{progress.done} / {progress.total}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-hover">
            <div className="h-full rounded-full bg-brand-500 transition-[width] duration-300" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : null}
      {error ? <p role="alert" className="mt-4 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p> : null}
      <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <Button variant="ghost" onClick={onBack} disabled={running}>Назад</Button>
        <Button onClick={run} isLoading={running} disabled={!keys.length || (updateKeys.length > 0 && !confirmed)}>
          Импортировать {keys.length}
        </Button>
      </div>
    </Card>
  )
}

function ImportResults({ batch, onReset }: { batch: Batch; onReset?: () => void }) {
  const { showToast } = useToast()
  const results = Object.entries(batch.results).map(([key, r]) => ({ key, ...r })).sort((a, b) => a.kind.localeCompare(b.kind) || a.row - b.row)
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Summary label="Создано" value={batch.created_count} tone="success" />
        <Summary label="Обновлено" value={batch.updated_count} tone="info" />
        <Summary label="Пропущено" value={batch.skipped_count} tone="warning" />
        <Summary label="С ошибками" value={batch.failed_count} tone="danger" />
      </div>
      <Card padding="none" title="Результат по строкам" actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" leftIcon={<Download className="size-4" />}
            onClick={() => importApi.downloadErrors(batch.id).catch((err) => showToast(extractErrorMessage(err), 'error'))}>Отчёт об ошибках</Button>
          {onReset ? <Button size="sm" leftIcon={<Upload className="size-4" />} onClick={onReset}>Новый файл</Button> : null}
        </div>
      }>
        {results.length ? (
          <ul className="divide-y divide-border">
            {results.map((r) => (
              <li key={r.key} className="flex flex-col gap-1.5 px-4 py-3 sm:flex-row sm:items-start sm:justify-between sm:px-5">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{r.title || 'без названия'}</p>
                  <p className="text-xs text-ink-muted">{KIND_LABEL[r.kind]} · строка {r.row} · {r.message}</p>
                  {r.verification_note ? <p className="mt-1 text-xs text-warning">Проверить: {r.verification_note}</p> : null}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge tone={RESULT_TONE[r.result]}>{RESULT_LABEL[r.result]}</Badge>
                  {r.object_id && r.result !== 'failed' ? (
                    <Link to={`${EDIT_PATH[r.kind]}?edit=${r.object_id}`} className="text-sm font-medium text-brand-700 hover:underline">Открыть</Link>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : <EmptyState className="py-10" title="Строки не импортировались" />}
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

const STATUS_TONE: Record<BatchSummary['status'], 'success' | 'warning' | 'danger' | 'muted' | 'info'> = {
  completed: 'success', partial: 'warning', failed: 'danger', importing: 'info', preview: 'muted', cancelled: 'muted',
}

function ImportHistory() {
  const { showToast } = useToast()
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<number | null>(null)
  const query = useQuery({ queryKey: ['site-import', 'history', page], queryFn: () => importApi.history(page) })
  const detail = useQuery({ queryKey: ['site-import', 'batch', openId], queryFn: () => importApi.batch(openId!), enabled: openId !== null })

  if (query.isPending) return <LoadingState />
  if (query.isError) return <ErrorState message={extractErrorMessage(query.error)} onRetry={() => query.refetch()} />
  const items = query.data.results
  if (!items.length) return <EmptyState icon={History} title="Импортов пока не было" description="Здесь появятся загруженные файлы и их результаты." />

  return (
    <div className="space-y-5">
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[52rem] text-sm">
            <thead className="bg-surface-muted text-left text-xs text-ink-muted uppercase">
              <tr>
                <th className="px-4 py-2.5">Дата</th>
                <th className="px-2 py-2.5">Администратор</th>
                <th className="px-2 py-2.5">Файл</th>
                <th className="px-2 py-2.5 text-right">Строк</th>
                <th className="px-2 py-2.5 text-right">Импорт.</th>
                <th className="px-2 py-2.5 text-right">Пропущ.</th>
                <th className="px-2 py-2.5 text-right">Ошибки</th>
                <th className="px-2 py-2.5">Статус</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((b) => (
                <tr key={b.id} className={cn(openId === b.id && 'bg-brand-50/50')}>
                  <td className="px-4 py-2.5 whitespace-nowrap">{formatDate(b.created_at)}</td>
                  <td className="px-2 py-2.5">{b.created_by_name || '—'}</td>
                  <td className="max-w-[16rem] px-2 py-2.5">
                    <p className="truncate font-medium text-ink">{b.file_name}</p>
                    <p className="text-xs text-ink-muted">{b.content_type_label}</p>
                  </td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{b.total_rows}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{b.imported_count}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{b.skipped_count}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{b.failed_count}</td>
                  <td className="px-2 py-2.5"><Badge tone={STATUS_TONE[b.status]}>{b.status_label}</Badge></td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setOpenId(openId === b.id ? null : b.id)}>{openId === b.id ? 'Скрыть' : 'Подробно'}</Button>
                      <Button variant="ghost" size="sm" aria-label="Отчёт об ошибках (CSV)" title="Отчёт об ошибках (CSV)"
                        onClick={() => importApi.downloadErrors(b.id).catch((err) => showToast(extractErrorMessage(err), 'error'))}>
                        <Download className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Pagination page={page} pageSize={20} totalCount={query.data.count} onPageChange={setPage} />
      {openId !== null ? (
        detail.isPending ? <LoadingState /> : detail.isError ? <ErrorState message={extractErrorMessage(detail.error)} /> : <ImportResults batch={detail.data} />
      ) : null}
    </div>
  )
}
