import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import type { ReportData, ReportValue, SchemaColumn, SchemaField } from '@/types/worklog'
import { cn } from '@/utils/cn'
import { formatDate } from '@/utils/format'

import { Field } from './formUi'

type Row = Record<string, string>

function asText(value: ReportValue | undefined): string {
  if (value == null) return ''
  if (Array.isArray(value)) return (value as string[]).join('\n')
  return String(value)
}

function asRows(value: ReportValue | undefined): Row[] {
  return Array.isArray(value) && value.every((v) => typeof v === 'object') ? (value as Row[]) : []
}

function ScoreInput({ id, value, onChange }: { id: string; value: ReportValue | undefined; onChange: (v: number | '') => void }) {
  return (
    <div id={id} role="radiogroup" className="flex gap-1.5">
      {[1, 2, 3, 4, 5].map((score) => {
        const selected = Number(value) === score
        return (
          <button
            key={score}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={String(score)}
            onClick={() => onChange(selected ? '' : score)}
            className={cn(
              'size-10 rounded-lg border text-sm font-medium transition-colors',
              selected ? 'border-brand-500 bg-brand-500 text-white' : 'border-border bg-surface text-ink hover:bg-surface-hover',
            )}
          >
            {score}
          </button>
        )
      })}
    </div>
  )
}

function CellInput({ column, value, onChange, id }: { column: SchemaColumn; value: string; onChange: (v: string) => void; id: string }) {
  if (column.type === 'date') {
    return <DatePicker id={id} aria-label={column.label} value={value} onChange={(e) => onChange(e.target.value)} />
  }
  return <Input id={id} aria-label={column.label} value={value} onChange={(e) => onChange(e.target.value)} />
}

function RowsInput({ field, value, onChange }: { field: SchemaField; value: Row[]; onChange: (rows: Row[]) => void }) {
  const columns = field.columns ?? []
  const rows = value.length ? value : [{}]
  const update = (index: number, key: string, cell: string) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, [key]: cell } : row)))
  return (
    <div className="space-y-2">
      {rows.map((row, index) => (
        <div key={index} className="grid items-end gap-2 rounded-lg border border-border p-3 sm:grid-cols-[repeat(4,minmax(0,1fr))_auto]">
          {columns.map((column) => (
            <div key={column.key} className="min-w-0">
              <span className="mb-1 block text-xs text-ink-muted">{column.label}</span>
              <CellInput
                id={`${field.key}-${index}-${column.key}`}
                column={column}
                value={row[column.key] ?? ''}
                onChange={(cell) => update(index, column.key, cell)}
              />
            </div>
          ))}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Удалить строку"
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
      ))}
      <Button type="button" variant="secondary" size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => onChange([...rows, {}])}>
        Добавить строку
      </Button>
    </div>
  )
}

/** One form field of a report, rendered from its schema (apps.worklog.schemas). */
export function ReportFieldInput({
  field,
  value,
  onChange,
  error,
}: {
  field: SchemaField
  value: ReportValue | undefined
  onChange: (value: ReportValue) => void
  error?: string
}) {
  const id = `report-${field.key}`
  let control
  switch (field.type) {
    case 'textarea':
      control = <Textarea id={id} rows={3} value={asText(value)} onChange={(e) => onChange(e.target.value)} placeholder={field.placeholder} />
      break
    case 'list':
      control = <Textarea id={id} rows={3} value={asText(value)} onChange={(e) => onChange(e.target.value)} placeholder="Каждый пункт с новой строки" />
      break
    case 'date':
      control = <DatePicker id={id} value={asText(value)} onChange={(e) => onChange(e.target.value)} />
      break
    case 'number':
    case 'percent':
      control = (
        <Input id={id} type="number" min={0} max={field.type === 'percent' ? 100 : undefined} inputMode="decimal" value={asText(value)} onChange={(e) => onChange(e.target.value)} />
      )
      break
    case 'score':
      control = <ScoreInput id={id} value={value} onChange={onChange} />
      break
    case 'select':
      control = (
        <Select id={id} value={asText(value)} onChange={(e) => onChange(e.target.value)} placeholder="Не выбрано" options={(field.options ?? []).map((o) => ({ value: o, label: o }))} />
      )
      break
    case 'multiselect': {
      const selected = Array.isArray(value) ? (value as string[]) : []
      control = (
        <div id={id} className="flex flex-wrap gap-2">
          {(field.options ?? []).map((option) => (
            <label key={option} className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(option)}
                onChange={(e) => onChange(e.target.checked ? [...selected, option] : selected.filter((v) => v !== option))}
              />
              {option}
            </label>
          ))}
        </div>
      )
      break
    }
    case 'rows':
      control = <RowsInput field={field} value={asRows(value)} onChange={onChange} />
      break
    default:
      control = <Input id={id} value={asText(value)} onChange={(e) => onChange(e.target.value)} placeholder={field.placeholder} />
  }
  return (
    <Field label={field.label} htmlFor={field.type === 'score' || field.type === 'multiselect' ? undefined : id} error={error} required={field.required} help={field.help}>
      {control}
    </Field>
  )
}

/** The same field, read only. */
export function ReportFieldValue({ field, value }: { field: SchemaField; value: ReportValue | undefined }) {
  let shown: React.ReactNode = '—'
  if (field.type === 'rows') {
    const rows = asRows(value)
    if (rows.length) {
      shown = (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>{(field.columns ?? []).map((c) => <th key={c.key}>{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {(field.columns ?? []).map((c) => (
                    <td key={c.key}>{c.type === 'date' && row[c.key] ? formatDate(row[c.key]) : (row[c.key] ?? '—')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
  } else if (Array.isArray(value) && value.length) {
    shown = (
      <ul className="list-disc space-y-0.5 pl-5">
        {(value as string[]).map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    )
  } else if (value !== undefined && value !== '' && !Array.isArray(value)) {
    shown = field.type === 'date' ? formatDate(String(value)) : field.type === 'score' ? `${value} из 5` : String(value)
  }
  return (
    <div className="grid gap-1 sm:grid-cols-[14rem_1fr] sm:gap-4">
      <dt className="text-sm font-medium text-ink-muted">{field.label}</dt>
      <dd className="whitespace-pre-line text-sm text-ink">{shown}</dd>
    </div>
  )
}

/** Drop empty values before sending; the backend normalizes the rest. */
export function cleanData(data: ReportData): ReportData {
  const out: ReportData = {}
  for (const [key, value] of Object.entries(data)) {
    if (value === '' || value == null) continue
    if (Array.isArray(value) && value.length === 0) continue
    out[key] = value
  }
  return out
}
