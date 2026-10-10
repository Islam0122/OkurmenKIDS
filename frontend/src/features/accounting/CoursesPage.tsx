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
import { useAccountingMutation, useAccountingOptions, useCourseSettings } from '@/hooks/useAccounting'
import { Field } from '@/features/worklog/formUi'
import type { AccountingOptions, CourseSettings } from '@/types/accounting'

import { BlockReviewSection } from './BlockReviewSection'
import { SubjectCyclesSection } from './SubjectCyclesSection'
import { formatDate, som, useRunner } from './shared'

/** Интервал начисления курса и циклы по предметам групп. Уроки каждого
 * предмета учитываются автоматически; на каждом пороге предмета тренерам,
 * которые вели его уроки, сразу создаются начисления. */
export function CoursesPage() {
  const options = useAccountingOptions()
  const settings = useCourseSettings()
  const [editing, setEditing] = useState<CourseSettings | 'new' | null>(null)
  const canEdit = options.data?.can_operate ?? false

  return (
    <div>
      <PageHeader
        title="Курсы и блоки"
        description="Проведённые уроки учитываются автоматически и отдельно по каждому предмету группы (IT, English, Soft Skills…). На каждом пороге предмета (12, 24, 36… — интервал курса) тренерам этого предмета начисляется: студенты × стоимость курса × процент / 100 × доля проведённых уроков."
        actions={canEdit ? <Button leftIcon={<Plus className="size-4" />} onClick={() => setEditing('new')}>Настроить курс</Button> : null}
      />

      {settings.isLoading ? <LoadingState /> : settings.isError ? <ErrorState onRetry={() => settings.refetch()} /> :
        settings.data?.results.length === 0 ? (
          <EmptyState title="Курсы не настроены" description="Укажите стоимость курса за студента и интервал начисления в уроках." />
        ) : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Курс</th><th className="text-right">Стоимость за студента</th><th className="text-right">Интервал, уроков</th><th>Учёт уроков</th><th>Предметы</th><th>Студенты</th><th>Несколько тренеров</th><th /></tr>
              </thead>
              <tbody>
                {settings.data?.results.map((c) => (
                  <tr key={c.id} className={c.is_active ? undefined : 'opacity-60'}>
                    <td className="font-medium text-ink">{c.course_name}{!c.is_active ? <Badge className="ml-2">отключён</Badge> : null}</td>
                    <td className="text-right">{som(c.current_price ?? c.price_per_student)}</td>
                    <td className="text-right">{c.required_lessons}</td>
                    <td>{c.count_lessons_from ? `с ${formatDate(c.count_lessons_from)}` : 'с первого урока'}</td>
                    <td className="text-xs">{c.counted_subjects_names.length ? c.counted_subjects_names.join(', ') : 'все предметы'}</td>
                    <td className="text-xs">{c.student_count_rule_display}</td>
                    <td className="text-xs">{c.trainer_split_rule_display}</td>
                    <td className="text-right">
                      {canEdit ? <Button size="sm" variant="ghost" leftIcon={<Pencil className="size-3.5" />} onClick={() => setEditing(c)}>Изменить</Button> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      <BlockReviewSection canOperate={canEdit} />

      <SubjectCyclesSection options={options.data} />

      {editing && options.data ? (
        <SettingsModal options={options.data} current={editing === 'new' ? null : editing}
          taken={(settings.data?.results ?? []).map((c) => c.course)} onClose={() => setEditing(null)} />
      ) : null}
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
    counted_subjects: current?.counted_subjects ?? [],
    trainer_split_rule: current?.trainer_split_rule ?? 'BY_LESSONS',
    is_active: current?.is_active ?? true,
  })
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(async (fn: () => Promise<unknown>) => fn())
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const { price_per_student, ...rest } = form
  // Стоимость задаётся только при создании; дальше — новой версией тарифа.
  const body = {
    ...(current ? rest : form),
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
        <p className="mb-3 text-sm text-ink-secondary">Новый интервал и предметы действуют на следующие циклы; завершённые циклы и утверждённые начисления не меняются. Стоимость меняется в разделе «Стоимость курсов».</p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {!current ? (
          <Field label="Курс" required htmlFor="cs-course" className="sm:col-span-2">
            <Select id="cs-course" value={form.course} placeholder="Выберите курс"
              options={options.courses.filter((c) => !taken.includes(c.id)).map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(e) => set({ course: e.target.value })} />
          </Field>
        ) : null}
        {!current ? (
          <Field label="Стоимость за студента в месяц, сом" required htmlFor="cs-price" help="Первая версия тарифа">
            <Input id="cs-price" type="number" min="0.01" step="0.01" value={price_per_student} onChange={(e) => set({ price_per_student: e.target.value })} />
          </Field>
        ) : null}
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
        <Field label="Несколько тренеров в цикле предмета" htmlFor="cs-split" className="sm:col-span-2"
          help="По умолчанию каждый тренер получает долю по своим проведённым урокам. Правило нужно подтвердить с руководством.">
          <Select id="cs-split" value={form.trainer_split_rule} options={options.trainer_split_rules}
            onChange={(e) => set({ trainer_split_rule: e.target.value as 'BY_LESSONS' | 'REVIEW' })} />
        </Field>
      </div>
      <fieldset className="mt-3">
        <legend className="field-label mb-1.5">Предметы с циклами</legend>
        <p className="mb-2 text-xs text-ink-muted">Циклы ведутся отдельно по каждому выбранному предмету (например, только IT). Ничего не выбрано — по всем предметам группы.</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {options.subjects.map((sub) => (
            <label key={sub.id} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={form.counted_subjects.includes(sub.id)}
                onChange={(e) => set({ counted_subjects: e.target.checked
                  ? [...form.counted_subjects, sub.id] : form.counted_subjects.filter((id) => id !== sub.id) })} />
              {sub.name}
            </label>
          ))}
        </div>
      </fieldset>
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
