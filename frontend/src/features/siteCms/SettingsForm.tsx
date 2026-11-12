import { useEffect, useState, type ReactNode } from 'react'
import { RotateCcw, Save } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { siteCmsApi, useSiteInvalidate, useSiteSettings } from './api'
import { snapshot } from './editorState'
import { ImageInput, imageRef, type ImageValue } from './fields'
import { LANGS, type Lang } from './schema'
import { Counter, FieldLabel, Hint, LangTabs, Panel, Skeleton } from './ui'

export interface SettingField {
  name: string
  label: string
  area?: boolean
  hint?: string
  /** Has _ky / _en translations (shown under the language switch). */
  i18n?: boolean
  image?: boolean
  max?: number
  type?: 'text' | 'url' | 'email' | 'tel'
  placeholder?: string
  wide?: boolean
}

/**
 * Форма общих настроек сайта (SiteSettings, /marketing/site/settings/):
 * главный экран, «Об академии», контакты, соцсети, SEO. Переключатель
 * языков хранит все три версии сразу — данные не теряются.
 */
export function SettingsForm({ title, description, fields, extra, children }: {
  title?: string
  description?: string
  fields: SettingField[]
  /** Extra values (featured lists…) the caller edits; included in the save. */
  extra?: { values: Record<string, unknown>; dirty: boolean; reset: () => void }
  children?: (values: Record<string, unknown>, set: (n: string, v: unknown) => void, lang: Lang) => ReactNode
}) {
  const { showToast } = useToast()
  const invalidate = useSiteInvalidate()
  const settings = useSiteSettings()
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [base, setBase] = useState<Record<string, unknown>>({})
  const [lang, setLang] = useState<Lang>('ru')
  const [saving, setSaving] = useState(false)
  const namesKey = fields.map((f) => `${f.name}:${f.i18n ? 1 : 0}:${f.image ? 1 : 0}`).join('|')
  useEffect(() => {
    if (!settings.data) return
    const picked: Record<string, unknown> = {}
    for (const part of namesKey ? namesKey.split('|') : []) {
      const [name, i18n, image] = part.split(':')
      for (const n of i18n === '1' ? [name, `${name}_ky`, `${name}_en`] : [name]) picked[n] = image === '1' ? undefined : settings.data[n] ?? ''
    }
    setValues(picked)
    setBase(picked)
  }, [settings.data, namesKey])
  const dirty = snapshot(values) !== snapshot(base) || Boolean(extra?.dirty)
  useEffect(() => {
    if (!dirty) return
    const onUnload = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [dirty])

  if (settings.isError) return <ErrorState message={extractErrorMessage(settings.error)} onRetry={() => settings.refetch()} />
  if (settings.isPending) {
    return <div className="space-y-4 rounded-2xl border border-border bg-surface p-5" role="status" aria-label="Загрузка"><Skeleton className="h-5 w-40" /><Skeleton className="h-10 w-full" /><Skeleton className="h-24 w-full" /></div>
  }
  const set = (n: string, v: unknown) => setValues((p) => ({ ...p, [n]: v }))
  const hasI18n = fields.some((f) => f.i18n)

  const save = async () => {
    setSaving(true)
    try {
      const body: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(values)) if (v !== undefined) body[k] = imageRef(v)
      const lists = extra ? Object.fromEntries(Object.entries(extra.values).filter(([, v]) => Array.isArray(v))) : {}
      const scalars = extra ? Object.fromEntries(Object.entries(extra.values).filter(([, v]) => !Array.isArray(v))) : {}
      Object.assign(body, scalars)
      if (Object.values(body).some((v) => v instanceof File)) {
        // multipart cannot carry an empty list — lists go in a second JSON request
        await siteCmsApi.saveSettings(body)
        if (Object.keys(lists).length) await siteCmsApi.saveSettings(lists)
      } else {
        await siteCmsApi.saveSettings({ ...body, ...lists })
      }
      await invalidate()
      showToast('Сохранено — изменения уже на сайте', 'success')
    } catch (error) {
      showToast(extractErrorMessage(error), 'error')
    } finally {
      setSaving(false)
    }
  }

  const shown = lang === 'ru' ? fields : fields.filter((f) => f.i18n)
  return (
    <Panel title={title} description={description} actions={hasI18n ? <LangTabs value={lang} onChange={setLang} /> : undefined}>
      <div className="space-y-5">
        {lang !== 'ru' ? <p className="rounded-lg bg-surface-muted px-3 py-2 text-xs text-ink-secondary">{LANGS.find((l) => l.code === lang)?.name}: пустое поле — на сайте будет русский текст.</p> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          {shown.map((f) => {
            const name = lang === 'ru' || !f.i18n ? f.name : `${f.name}_${lang}`
            const value = String(values[name] ?? '')
            return (
              <div key={name} className={cn((f.area || f.image || f.wide) && 'sm:col-span-2')}>
                <FieldLabel htmlFor={`s-${name}`} aside={f.max ? <Counter value={value} max={f.max} /> : undefined}>
                  {f.label}{lang !== 'ru' && f.i18n ? ` (${LANGS.find((l) => l.code === lang)?.label})` : ''}
                </FieldLabel>
                {f.image ? (
                  <div className="max-w-xl">
                    <ImageInput id={`s-${name}`} current={(settings.data?.[f.name] as string | null) ?? null} value={values[name] as ImageValue} onChange={(v) => set(name, v)} />
                  </div>
                ) : f.area ? (
                  <Textarea id={`s-${name}`} rows={4} value={value} onChange={(e) => set(name, e.target.value)}
                    placeholder={lang !== 'ru' ? String(values[f.name] ?? '').slice(0, 120) : f.placeholder} />
                ) : (
                  <Input id={`s-${name}`} type={f.type ?? 'text'} value={value} onChange={(e) => set(name, e.target.value)}
                    placeholder={lang !== 'ru' && f.i18n ? String(values[f.name] ?? '') : f.placeholder} />
                )}
                {f.hint && (lang === 'ru' || !f.i18n) ? <Hint>{f.hint}</Hint> : null}
              </div>
            )
          })}
        </div>
        {children?.(values, set, lang)}
        <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-end">
          {dirty ? <span className="text-xs font-medium text-cms-gold-deep sm:mr-auto">Есть несохранённые изменения</span> : <span className="text-xs text-ink-muted sm:mr-auto">Изменения появляются на сайте сразу после сохранения.</span>}
          {dirty ? <Button variant="ghost" leftIcon={<RotateCcw className="size-4" aria-hidden />} onClick={() => { setValues(base); extra?.reset() }}>Отменить изменения</Button> : null}
          <Button leftIcon={<Save className="size-4" aria-hidden />} isLoading={saving} disabled={!dirty} onClick={save}>Сохранить</Button>
        </div>
      </div>
    </Panel>
  )
}
