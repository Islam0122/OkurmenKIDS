/**
 * Pure helpers of the content editor: form values of a record (all three
 * languages at once — switching the language never drops anything), the
 * request body, what is missing, how complete each language is, and the
 * local draft backup.
 */
import type { Body, Choice, Row } from './api'
import { imageRef } from './fields'
import type { FieldDef, Lang, ResourceDef } from './schema'

export type Values = Record<string, unknown>

export const NULLABLE_SELECT = (f: FieldDef) => Boolean(f.choices?.startsWith('lms:') || f.choices === 'branches')

function emptyValue(f: FieldDef): unknown {
  if (f.type === 'boolean') return f.name === 'is_active' || f.name === 'is_visible'
  if (f.type === 'number' || f.type === 'datetime') return null
  if (f.type === 'select') return NULLABLE_SELECT(f) ? null : ''
  if (f.type === 'date') return new Date().toISOString().slice(0, 10)
  return ''
}

export function initialValues(def: ResourceDef, row: Row | null, choices?: (source?: string) => Choice[]): Values {
  const values: Values = {}
  for (const f of def.fields) {
    if (f.type === 'image') {
      values[f.name] = undefined // undefined = unchanged
      continue
    }
    const current = row?.[f.name]
    values[f.name] = current === undefined || (current === null && !NULLABLE_SELECT(f) && f.type !== 'number' && f.type !== 'datetime') ? emptyValue(f) : current
    if (f.type === 'number' && typeof values[f.name] === 'number') values[f.name] = String(values[f.name])
    if (!row && f.type === 'select' && f.required && !values[f.name]) values[f.name] = choices?.(f.choices)[0]?.value ?? ''
    if (f.type === 'select' && values[f.name] !== null && values[f.name] !== '') values[f.name] = String(values[f.name])
    if (f.translatable) for (const l of ['ky', 'en']) values[`${f.name}_${l}`] = row?.[`${f.name}_${l}`] ?? ''
  }
  if (def.workflow) values.published_at = row?.published_at ?? null
  if (def.seo) {
    values.seo_title = row?.seo_title ?? ''
    values.seo_description = row?.seo_description ?? ''
  }
  if (!row && def.key === 'testimonials') values.language = 'ru'
  if (!row && def.key === 'team') values.category = 'teacher'
  return values
}

export function buildBody(def: ResourceDef, values: Values): Body {
  const out: Body = {}
  for (const [key, raw] of Object.entries(values)) {
    const value = imageRef(raw)
    if (value === undefined) continue
    const field = def.fields.find((f) => f.name === key)
    if (field && field.type === 'select' && NULLABLE_SELECT(field) && value !== null) out[key] = Number(value)
    else if (field && field.type === 'number') out[key] = value === '' || value === null ? null : Number(value)
    else out[key] = value
  }
  if (!out.published_at) delete out.published_at
  return out
}

/** Comparable form of the values (files by name/size — they are not in the baseline anyway). */
export function snapshot(values: Values): string {
  return JSON.stringify(values, (_key, v) => (v instanceof File ? `file:${v.name}:${v.size}` : v))
}

export const isEmpty = (v: unknown) => v === null || v === undefined || (typeof v === 'string' && !v.trim())

export function missingFields(def: ResourceDef, values: Values, row: Row | null): FieldDef[] {
  return def.fields.filter((f) => {
    if (!f.required || f.type === 'boolean') return false
    if (f.type === 'image') return values[f.name] === null || (values[f.name] === undefined && !row?.[f.name])
    return isEmpty(values[f.name])
  })
}

/** How complete a language is: every translatable field that has Russian text. */
export function langFill(def: ResourceDef, values: Values): Record<Lang, 'full' | 'partial' | 'empty'> {
  const fields = def.fields.filter((f) => f.translatable && !isEmpty(values[f.name]))
  const state = (lang: 'ky' | 'en') => {
    if (!fields.length) return 'empty' as const
    const n = fields.filter((f) => !isEmpty(values[`${f.name}_${lang}`])).length
    return n === 0 ? 'empty' as const : n === fields.length ? 'full' as const : 'partial' as const
  }
  const ru = def.fields.filter((f) => f.translatable)
  const ruState = ru.every((f) => !isEmpty(values[f.name])) ? 'full' as const : ru.some((f) => !isEmpty(values[f.name])) ? 'partial' as const : 'empty' as const
  return { ru: ruState, ky: state('ky'), en: state('en') }
}

/** After a save: take the server's values where the form still holds what was sent, keep newer edits. */
export function mergeSaved(current: Values, sent: Values, saved: Values): Values {
  const out: Values = { ...current }
  for (const key of Object.keys(saved)) {
    if (snapshot({ v: current[key] }) === snapshot({ v: sent[key] })) out[key] = saved[key]
  }
  return out
}

// --- Local backup (the browser keeps unsaved edits if the tab closes) ------

const BACKUP_PREFIX = 'okurmen-cms-draft:'

export interface Backup {
  values: Values
  at: number
  /** updated_at of the server version the edits started from. */
  base: string | null
}

export const backupKey = (resource: string, id: number | null) => `${BACKUP_PREFIX}${resource}:${id ?? 'new'}`

export function readBackup(key: string): Backup | null {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as Backup) : null
  } catch {
    return null
  }
}

export function writeBackup(key: string, backup: Backup | null) {
  try {
    if (!backup) window.localStorage.removeItem(key)
    else {
      // Files cannot be stored: an unsaved upload is simply not in the backup.
      const values = Object.fromEntries(Object.entries(backup.values).filter(([, v]) => !(v instanceof File)))
      window.localStorage.setItem(key, JSON.stringify({ ...backup, values }))
    }
  } catch {
    /* storage full or blocked — the server copy is the source of truth */
  }
}
