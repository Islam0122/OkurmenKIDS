import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Settings2 } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useProgram, usePrograms, useProgressMeta, useSaveProgram } from '@/hooks/useAcademicProgress'
import { extractErrorMessage } from '@/lib/apiError'
import type { ProgramDetail, ProgramInput, Ref } from '@/types/academicProgress'
import { cn } from '@/utils/cn'

const TH = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-ink-muted'
const TD = 'border-t border-border px-3 py-2.5'

/**
 * «Настройки учебной программы»: how many lessons make a study month, how
 * many months, the main and extra subjects and each month's own subject and
 * plan. Operations director — every program; Team Lead — their directions;
 * others — view only (backend: apps.academic_progress.access).
 */
export function ProgramSettingsPage() {
  const { data, isPending, isError, refetch } = usePrograms()
  const [open, setOpen] = useState<number | null>(null)

  return (
    <div className="space-y-5">
      <PageHeader title="Настройки учебной программы" description="Учебные месяцы программ: предмет и число занятий в каждом месяце" />
      {isPending ? <LoadingState /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.length === 0 ? <EmptyState title="Программ нет" /> : null}
      {data && data.length ? (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-surface-muted">
              <tr>{['Программа', 'Основной предмет', 'Дополнительные', 'Занятий в месяце', 'Месяцев', 'Всего', 'Группы', ''].map((h, i) => <th key={i} className={TH}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td className={cn(TD, 'font-medium text-ink')}>{p.name}</td>
                  <td className={TD}>{p.main_subject?.name ?? '—'}</td>
                  <td className={cn(TD, 'text-ink-secondary')}>{p.extra_subjects.map((s) => s.name).join(', ') || '—'}</td>
                  <td className={TD}>{p.lessons_per_month ?? '—'}</td>
                  <td className={TD}>{p.duration_months ?? '—'}</td>
                  <td className={TD}>{p.total_lessons ?? '—'}</td>
                  <td className={TD}>
                    {p.groups}
                    {p.groups_need_setup ? (
                      <span className="ml-2 inline-flex items-center gap-1 text-xs text-warning" title="Группы со статусом «Требуется настройка»">
                        <AlertTriangle className="size-3.5" aria-hidden />{p.groups_need_setup}
                      </span>
                    ) : null}
                  </td>
                  <td className={cn(TD, 'text-right')}>
                    {!p.configured ? <span className="mr-3 text-xs text-warning">Не настроено</span> : null}
                    <Button size="sm" variant={p.configured ? 'secondary' : 'primary'} leftIcon={<Settings2 className="size-4" aria-hidden />} onClick={() => setOpen(p.id)}>
                      {p.can_edit ? (p.configured ? 'Изменить' : 'Настроить') : 'Открыть'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <ProgramEditor courseId={open} onClose={() => setOpen(null)} />
    </div>
  )
}

function ProgramEditor({ courseId, onClose }: { courseId: number | null; onClose: () => void }) {
  const { data } = useProgram(courseId)
  return (
    <Modal isOpen={courseId !== null} onClose={onClose} title={data ? `Программа ${data.course.name}` : 'Программа'} size="lg">
      {!data ? <LoadingState /> : <EditorForm key={data.course.id} detail={data} onClose={onClose} />}
    </Modal>
  )
}

type MonthRow = { subject: string; planned: string }

function EditorForm({ detail, onClose }: { detail: ProgramDetail; onClose: () => void }) {
  const meta = useProgressMeta()
  const save = useSaveProgram(detail.course.id)
  const { showToast } = useToast()
  const s = detail.settings
  const presetOf = (n: number) => (n === 12 || n === 20 ? String(n) : 'custom')
  const [perMonth, setPerMonth] = useState(String(s?.lessons_per_month ?? 12))
  const [preset, setPreset] = useState(presetOf(s?.lessons_per_month ?? 12))
  const [duration, setDuration] = useState(String(s?.duration_months ?? 6))
  const [main, setMain] = useState(String(s?.main_subject?.id ?? ''))
  const [extra, setExtra] = useState<number[]>(s?.extra_subjects.map((x) => x.id) ?? [])
  const [mode, setMode] = useState<'main' | 'all'>(s?.count_mode ?? 'main')
  const [months, setMonths] = useState<Record<number, MonthRow>>(() =>
    Object.fromEntries((s?.months ?? []).map((m) => [m.number, { subject: String(m.subject?.id ?? ''), planned: m.planned_lessons ? String(m.planned_lessons) : '' }])))
  const [errors, setErrors] = useState<Record<string, unknown>>({})
  const readOnly = !detail.can_edit

  useEffect(() => {
    if (preset !== 'custom') setPerMonth(preset)
  }, [preset])

  const subjects: Ref[] = useMemo(() => {
    const all = meta.data?.subjects ?? detail.course.subjects
    const ids = new Set(all.map((x) => x.id))
    return [...all, ...detail.course.subjects.filter((x) => !ids.has(x.id))]
  }, [meta.data, detail.course.subjects])
  const subjectName = (id: string) => subjects.find((x) => String(x.id) === id)?.name
  const count = Math.max(0, Math.min(60, Number(duration) || 0))
  const total = Array.from({ length: count }, (_, i) => Number(months[i + 1]?.planned) || Number(perMonth) || 0).reduce((a, b) => a + b, 0)

  const submit = () => {
    const payload: ProgramInput = {
      lessons_per_month: Number(perMonth),
      duration_months: Number(duration),
      main_subject: main ? Number(main) : null,
      extra_subjects: extra,
      count_mode: mode,
      months: Object.entries(months)
        .filter(([n, m]) => Number(n) <= count && (m.subject || m.planned))
        .map(([n, m]) => ({ number: Number(n), subject: m.subject ? Number(m.subject) : null, planned_lessons: m.planned ? Number(m.planned) : null })),
    }
    save.mutate(payload, {
      onSuccess: () => { showToast('Настройки программы сохранены', 'success'); onClose() },
      onError: (error) => {
        const data = (error as { response?: { data?: Record<string, unknown> } }).response?.data
        if (data && typeof data === 'object') setErrors(data)
        showToast(extractErrorMessage(error, 'Не удалось сохранить настройки'), 'error')
      },
    })
  }
  const err = (field: string) => (typeof errors[field] === 'string' ? <p className="mt-1 text-xs text-danger">{errors[field] as string}</p> : null)

  return (
    <div className="space-y-5">
      <fieldset disabled={readOnly} className="space-y-5">
        <div>
          <p className="mb-2 text-sm font-medium text-ink">Занятий в одном учебном месяце</p>
          <div className="flex flex-wrap items-center gap-3">
            <SegmentedControl aria-label="Занятий в месяце" value={preset} onChange={setPreset}
              options={[{ value: '12', label: '12 занятий' }, { value: '20', label: '20 занятий' }, { value: 'custom', label: 'Другое' }]} />
            {preset === 'custom' ? (
              <input aria-label="Своё количество занятий" type="number" min={1} max={200} className="form-control w-24" value={perMonth} onChange={(e) => setPerMonth(e.target.value)} />
            ) : null}
          </div>
          {err('lessons_per_month')}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-ink">Продолжительность, месяцев</span>
            <input type="number" min={1} max={60} className="form-control" value={duration} onChange={(e) => setDuration(e.target.value)} />
            {err('duration_months')}
          </label>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-ink">Основной предмет</span>
            <Select aria-label="Основной предмет" placeholder="Не выбран" value={main} onChange={(e) => setMain(e.target.value)}
              options={subjects.map((x) => ({ value: String(x.id), label: x.name }))} />
          </label>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-ink">Дополнительные предметы</p>
          <div className="flex flex-wrap gap-2">
            {subjects.filter((x) => String(x.id) !== main).map((x) => {
              const on = extra.includes(x.id)
              return (
                <button key={x.id} type="button" aria-pressed={on} onClick={() => setExtra(on ? extra.filter((i) => i !== x.id) : [...extra, x.id])}
                  className={cn('rounded-full border px-3 py-1 text-sm', on ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-border text-ink-secondary hover:bg-surface-hover')}>
                  {x.name}
                </button>
              )
            })}
          </div>
          {err('extra_subjects')}
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-ink">Какие занятия заполняют учебный месяц</p>
          <SegmentedControl aria-label="Какие занятия считать" value={mode} onChange={setMode}
            options={[{ value: 'main', label: 'Только основные предметы' }, { value: 'all', label: 'Все предметы' }]} />
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-ink">Учебные месяцы <span className="font-normal text-ink-muted">· пустое поле — значение по умолчанию</span></p>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[420px] text-sm">
              <thead className="bg-surface-muted">
                <tr><th className={TH}>Месяц</th><th className={TH}>Основной предмет</th><th className={TH}>План занятий</th></tr>
              </thead>
              <tbody>
                {Array.from({ length: count }, (_, i) => i + 1).map((n) => {
                  const row = months[n] ?? { subject: '', planned: '' }
                  const set = (patch: Partial<MonthRow>) => setMonths({ ...months, [n]: { ...row, ...patch } })
                  return (
                    <tr key={n}>
                      <td className={cn(TD, 'whitespace-nowrap font-medium text-ink')}>{n}-й месяц</td>
                      <td className={TD}>
                        <Select aria-label={`Предмет ${n}-го месяца`} placeholder={subjectName(main) ? `${subjectName(main)} (основной)` : 'Основной предмет'}
                          value={row.subject} onChange={(e) => set({ subject: e.target.value })} options={subjects.map((x) => ({ value: String(x.id), label: x.name }))} />
                      </td>
                      <td className={TD}>
                        <input aria-label={`План ${n}-го месяца`} type="number" min={1} max={200} placeholder={perMonth} className="form-control w-24"
                          value={row.planned} onChange={(e) => set({ planned: e.target.value })} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {errors.months ? <p className="mt-1 text-xs text-danger">Проверьте учебные месяцы.</p> : null}
          <p className="mt-2 text-sm text-ink-secondary">Всего по плану: <b className="text-ink">{total}</b> занятий</p>
        </div>
      </fieldset>

      <p className="text-xs text-ink-muted">
        Изменение настроек пересчитывает учебный месяц групп по уже проведённым занятиям — занятия, посещаемость и история не меняются.
        {detail.settings?.updated_by ? ` Последнее изменение: ${detail.settings.updated_by}.` : ''}
      </p>
      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <Button variant="secondary" onClick={onClose}>{readOnly ? 'Закрыть' : 'Отменить'}</Button>
        {!readOnly ? <Button onClick={submit} isLoading={save.isPending} disabled={!Number(perMonth) || !count}>Сохранить</Button> : null}
      </div>
    </div>
  )
}
