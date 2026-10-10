import { useState } from 'react'
import { Pencil, Plus } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Tabs } from '@/components/ui/Tabs'
import { useAccountingMutation, useAccountingOptions, useCourseCycles, useCourseSettings } from '@/hooks/useAccounting'
import { Field } from '@/features/worklog/formUi'
import type { AccountingOptions, CourseCycle, CourseSettings } from '@/types/accounting'

import { Section, formatDate, som, useRunner } from './shared'

type CycleTab = 'IN_PROGRESS' | 'COMPLETED' | 'INVALIDATED'

const EMPTY: Record<CycleTab, string> = {
  IN_PROGRESS: 'Незавершённых циклов нет',
  COMPLETED: 'Завершённых циклов нет',
  INVALIDATED: 'Отменённых циклов нет',
}

const ACCRUAL_TONE = {
  ACCRUED: 'info',
  APPROVED: 'success',
  CANCELLED: 'muted',
  CORRECTED: 'warning',
  CORRECTION_REQUIRED: 'danger',
} as const

/** Интервал начисления курса и циклы групп. Уроки учитываются автоматически;
 * на каждом пороге тренеру сразу создаётся начисление. Незавершённые циклы —
 * отдельно: процент за них ещё не начисляется. */
export function CoursesPage() {
  const options = useAccountingOptions()
  const settings = useCourseSettings()
  const [tab, setTab] = useState<CycleTab>('IN_PROGRESS')
  const cycles = useCourseCycles({ status: tab })
  const [editing, setEditing] = useState<CourseSettings | 'new' | null>(null)
  const canEdit = options.data?.can_operate ?? false

  return (
    <div>
      <PageHeader
        title="Курсы и циклы"
        description="Проведённые уроки групп учитываются автоматически. На каждом пороге (12, 24, 36… — интервал курса) тренеру сразу начисляется: студенты × стоимость курса × процент / 100. Новый интервал действует на следующие циклы."
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setEditing('new')}>Настроить курс</Button> : null}
      />

      {settings.isLoading ? <LoadingState /> : settings.isError ? <ErrorState onRetry={() => settings.refetch()} /> :
        settings.data?.results.length === 0 ? (
          <EmptyState title="Курсы не настроены" description="Укажите стоимость курса за студента и интервал начисления в уроках." />
        ) : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Курс</th><th className="text-right">Стоимость за студента</th><th className="text-right">Интервал, уроков</th><th>Учёт уроков</th><th>Студенты</th><th /></tr>
              </thead>
              <tbody>
                {settings.data?.results.map((c) => (
                  <tr key={c.id} className={c.is_active ? undefined : 'opacity-60'}>
                    <td className="font-medium text-ink">{c.course_name}{!c.is_active ? <Badge className="ml-2">отключён</Badge> : null}</td>
                    <td className="text-right">{som(c.price_per_student)}</td>
                    <td className="text-right">{c.required_lessons}</td>
                    <td>{c.count_lessons_from ? `с ${formatDate(c.count_lessons_from)}` : 'с первого урока'}</td>
                    <td className="text-xs">{c.student_count_rule_display}</td>
                    <td className="text-right">
                      {canEdit ? <Button size="sm" variant="ghost" leftIcon={<Pencil className="size-3.5" />} onClick={() => setEditing(c)}>Изменить</Button> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      <Section title="Циклы групп">
        <Tabs
          aria-label="Циклы"
          items={[
            { key: 'IN_PROGRESS', label: 'Незавершённые' },
            { key: 'COMPLETED', label: 'Завершённые' },
            { key: 'INVALIDATED', label: 'Отменённые' },
          ] as const}
          value={tab}
          onChange={setTab}
        />
        <div className="mt-4">
          {cycles.isLoading ? <LoadingState /> : cycles.isError ? <ErrorState onRetry={() => cycles.refetch()} /> :
            cycles.data?.results.length === 0 ? <EmptyState title={EMPTY[tab]} /> :
              <CyclesTable rows={cycles.data!.results} completed={tab !== 'IN_PROGRESS'} />}
        </div>
      </Section>

      {editing && options.data ? (
        <SettingsModal options={options.data} current={editing === 'new' ? null : editing}
          taken={(settings.data?.results ?? []).map((c) => c.course)} onClose={() => setEditing(null)} />
      ) : null}
    </div>
  )
}

function CyclesTable({ rows, completed }: { rows: CourseCycle[]; completed: boolean }) {
  return (
    <div className="card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Группа</th><th>Курс</th><th>Цикл</th><th>Уроки</th><th>Тренер</th>
            {completed
              ? <><th>Порог достигнут</th><th className="text-right">Студенты</th><th className="text-right">База</th><th>Начисление</th></>
              : <th>Начат</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td className="font-medium text-ink">{c.group_name}</td>
              <td>{c.course_name}</td>
              <td>№{c.number}</td>
              <td>
                {completed ? (
                  <span>{c.lessons_total}<span className="block text-xs text-ink-muted">по {c.required_lessons} в цикле</span></span>
                ) : (
                  <span>{c.lessons_done} / {c.required_lessons} <span className="text-xs text-ink-muted">(всего {c.lessons_total})</span>
                    <span className="mt-1 block h-1.5 w-24 overflow-hidden rounded-full bg-surface-hover">
                      <span className="block h-full bg-brand-500" style={{ width: `${Math.min(100, (c.lessons_done / c.required_lessons) * 100)}%` }} />
                    </span>
                  </span>
                )}
              </td>
              <td className="text-sm">{c.trainers.join(', ') || '—'}</td>
              {completed ? (
                <>
                  <td>{formatDate(c.completed_on)}</td>
                  <td className="text-right">{c.student_count}</td>
                  <td className="text-right whitespace-nowrap">{c.student_count} × {som(c.course_price)} = {som(c.base_amount)}</td>
                  <td className="text-sm">
                    {c.invalidated_reason ? <p className="mb-1 text-xs text-warning">{c.invalidated_reason}</p> : null}
                    {c.accruals.length === 0 ? <Badge tone="warning">нет тренера с процентом</Badge> : c.accruals.map((a) => (
                      <div key={a.id} className="mb-1">
                        <p>{a.employee_name}: {som(a.amount)} ({Number(a.percentage)}%)</p>
                        <p className="flex flex-wrap items-center gap-1 text-xs text-ink-muted">
                          <Badge tone={ACCRUAL_TONE[a.status]}>{a.status_display}</Badge>
                          {a.period_label ? <span>{a.period_label}, {a.payroll_status_display}</span> : <span>ещё не в расчёте</span>}
                        </p>
                      </div>
                    ))}
                  </td>
                </>
              ) : <td>{formatDate(c.start_date)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SettingsModal({ options, current, taken, onClose }: {
  options: AccountingOptions
  current: CourseSettings | null
  taken: number[]
  onClose: () => void
}) {
  const [form, setForm] = useState({
    course: current ? String(current.course) : '',
    price_per_student: current?.price_per_student ?? '',
    required_lessons: current ? String(current.required_lessons) : '',
    count_lessons_from: current?.count_lessons_from ?? '',
    student_count_rule: current?.student_count_rule ?? 'ON_COMPLETION',
    is_active: current?.is_active ?? true,
  })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const body = {
    ...form,
    course: Number(form.course),
    required_lessons: Number(form.required_lessons),
    count_lessons_from: form.count_lessons_from || null,
  }
  const save = () => run(
    () => mutate.mutateAsync(() => (current ? accountingApi.updateCourseSettings(current.id, body) : accountingApi.createCourseSettings(body))),
    'Настройки курса сохранены',
  )

  return (
    <Modal isOpen onClose={onClose} title={current ? `Курс «${current.course_name}»` : 'Настроить курс'}>
      {current ? (
        <p className="mb-3 text-sm text-ink-secondary">Новый интервал и стоимость действуют на следующие циклы; завершённые циклы и утверждённые начисления не меняются.</p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {!current ? (
          <Field label="Курс" required htmlFor="cs-course" className="sm:col-span-2">
            <Select id="cs-course" value={form.course} placeholder="Выберите курс"
              options={options.courses.filter((c) => !taken.includes(c.id)).map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(e) => set({ course: e.target.value })} />
          </Field>
        ) : null}
        <Field label="Стоимость за студента, сом" required htmlFor="cs-price">
          <Input id="cs-price" type="number" min="0.01" step="0.01" value={form.price_per_student} onChange={(e) => set({ price_per_student: e.target.value })} />
        </Field>
        <Field label="Интервал начисления, уроков" required htmlFor="cs-lessons" help="12 → пороги 12, 24, 36…; 20 → 20, 40, 60…">
          <Input id="cs-lessons" type="number" min="1" value={form.required_lessons} onChange={(e) => set({ required_lessons: e.target.value })} />
        </Field>
        <Field label="Учитывать уроки с" htmlFor="cs-from" help="Необязательно. Пусто — с первого проведённого урока группы">
          <Input id="cs-from" type="date" value={form.count_lessons_from} onChange={(e) => set({ count_lessons_from: e.target.value })} />
        </Field>
        <Field label="Учитываемые студенты" htmlFor="cs-rule">
          <Select id="cs-rule" value={form.student_count_rule} options={options.student_count_rules}
            onChange={(e) => set({ student_count_rule: e.target.value })} />
        </Field>
      </div>
      {current ? (
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
          Учитывать циклы этого курса
        </label>
      ) : null}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Отмена</Button>
        <Button isLoading={busy} disabled={!form.course || !form.price_per_student || !(Number(form.required_lessons) >= 1)}
          onClick={async () => (await save()) && onClose()}>Сохранить</Button>
      </div>
    </Modal>
  )
}
