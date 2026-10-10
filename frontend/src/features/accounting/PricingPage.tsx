import { useState } from 'react'
import { Plus } from 'lucide-react'

import { accountingApi } from '@/api/accounting'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Field } from '@/features/worklog/formUi'
import { useAccountingMutation, useAccountingOptions, useCourseSettings, usePriceHistory } from '@/hooks/useAccounting'
import type { CourseSettings } from '@/types/accounting'

import { formatDate, formatDateTime, som, today, useRunner } from './shared'

/**
 * Стоимость курсов: фиксированная цена обучения одного ученика за месяц и
 * её история. Новая цена — новая версия с датой начала и причиной; старые
 * версии не редактируются, утверждённые начисления не меняются.
 */
export function PricingPage() {
  const options = useAccountingOptions()
  const settings = useCourseSettings()
  const [course, setCourse] = useState<number | undefined>(undefined)
  const history = usePriceHistory(course)
  const [creating, setCreating] = useState<CourseSettings | null | 'pick'>(null)
  const canEdit = options.data?.can_operate ?? false
  const courses = settings.data?.results ?? []

  return (
    <div>
      <PageHeader
        title="Стоимость курсов"
        description="Фиксированная стоимость обучения одного ученика за месяц — база процента тренера. Это согласованная цена, а не поступившие платежи. Каждое изменение сохраняется в истории с автором и причиной."
        actions={canEdit && courses.length ? (
          <Button leftIcon={<Plus className="size-4" />} onClick={() => setCreating('pick')}>Новый тариф</Button>
        ) : null}
      />

      {settings.isLoading ? <LoadingState /> : settings.isError ? <ErrorState onRetry={() => settings.refetch()} /> :
        courses.length === 0 ? (
          <EmptyState title="Курсы не настроены" description="Сначала задайте курс в разделе «Курсы и циклы»." />
        ) : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Курс</th><th className="text-right">Действует сегодня</th><th>Уроков в блоке</th><th /></tr>
              </thead>
              <tbody>
                {courses.map((c) => (
                  <tr key={c.id}>
                    <td className="font-medium text-ink">{c.course_name}</td>
                    <td className="text-right tabular-nums">{som(c.current_price ?? c.price_per_student)}</td>
                    <td>{c.required_lessons}</td>
                    <td className="whitespace-nowrap text-right">
                      <Button size="sm" variant="ghost" onClick={() => setCourse(c.course)}>История</Button>
                      {canEdit ? <Button size="sm" variant="ghost" onClick={() => setCreating(c)}>Изменить цену</Button> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      <section className="mt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-ink">История тарифов</h2>
          <FilterBar>
            <FilterField>
              <Select aria-label="Курс" value={course ? String(course) : ''} placeholder="Все курсы"
                options={courses.map((c) => ({ value: String(c.course), label: c.course_name }))}
                onChange={(e) => setCourse(Number(e.target.value) || undefined)} />
            </FilterField>
          </FilterBar>
        </div>
        {history.isLoading ? <LoadingState /> : history.isError ? <ErrorState onRetry={() => history.refetch()} /> :
          history.data?.results.length === 0 ? <EmptyState title="Изменений цены пока нет" /> : (
            <div className="card overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr><th>Курс</th><th className="text-right">Цена за ученика</th><th>Действует</th><th>Причина</th><th>Автор</th><th>Создано</th></tr>
                </thead>
                <tbody>
                  {history.data?.results.map((v) => (
                    <tr key={v.id}>
                      <td className="font-medium text-ink">
                        {v.course_name}
                        {v.is_current ? <Badge className="ml-2" tone="success">действует</Badge> : null}
                        {v.is_migrated ? <Badge className="ml-2" tone="warning">перенесено — проверьте</Badge> : null}
                      </td>
                      <td className="text-right tabular-nums">{som(v.price_per_student)}</td>
                      <td className="whitespace-nowrap">{formatDate(v.effective_from)} — {v.effective_to ? formatDate(v.effective_to) : 'без срока'}</td>
                      <td className="max-w-sm text-sm">{v.reason}</td>
                      <td>{v.created_by_name}</td>
                      <td className="whitespace-nowrap text-sm">{formatDateTime(v.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>

      {creating ? (
        <PriceModal courses={courses} current={creating === 'pick' ? null : creating} onClose={() => setCreating(null)} />
      ) : null}
    </div>
  )
}

function PriceModal({ courses, current, onClose }: { courses: CourseSettings[]; current: CourseSettings | null; onClose: () => void }) {
  const [form, setForm] = useState({
    course: current ? String(current.course) : '', price: '', effective_from: today(), reason: '',
  })
  const [confirming, setConfirming] = useState(false)
  const { run, busy } = useRunner()
  const mutate = useAccountingMutation(accountingApi.createPrice)
  const selected = courses.find((c) => String(c.course) === form.course)
  const valid = Boolean(form.course && Number(form.price) > 0 && form.effective_from && form.reason.trim())

  const submit = async () => {
    const ok = await run(() => mutate.mutateAsync({
      course: Number(form.course), price_per_student: form.price, effective_from: form.effective_from, reason: form.reason.trim(),
    }), 'Новый тариф сохранён')
    setConfirming(false)
    if (ok) onClose()
  }

  return (
    <>
      <Modal isOpen={!confirming} onClose={onClose} title={current ? `Новый тариф — ${current.course_name}` : 'Новый тариф'}>
        <p className="mb-3 text-sm text-ink-secondary">
          Цена действует с указанной даты для блоков, завершённых с этого дня. Уже созданные и утверждённые начисления
          не меняются; ввести цену задним числом на дату завершённого блока нельзя.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {!current ? (
            <Field label="Курс" required htmlFor="pr-course" className="sm:col-span-2">
              <Select id="pr-course" value={form.course} placeholder="Выберите курс"
                options={courses.map((c) => ({ value: String(c.course), label: c.course_name }))}
                onChange={(e) => setForm({ ...form, course: e.target.value })} />
            </Field>
          ) : null}
          <Field label="Цена за ученика в месяц, сом" required htmlFor="pr-price"
            help={selected ? `Сейчас: ${som(selected.current_price ?? selected.price_per_student)}` : undefined}>
            <Input id="pr-price" type="number" min="0.01" step="0.01" value={form.price}
              onChange={(e) => setForm({ ...form, price: e.target.value })} />
          </Field>
          <Field label="Действует с" required htmlFor="pr-from">
            <Input id="pr-from" type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
          </Field>
        </div>
        <Field label="Причина изменения" required htmlFor="pr-reason" className="mt-3">
          <Textarea id="pr-reason" rows={2} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </Field>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button disabled={!valid} onClick={() => setConfirming(true)}>Сохранить</Button>
        </div>
      </Modal>
      <ConfirmDialog
        isOpen={confirming}
        title="Подтвердите новый тариф"
        message={`${selected?.course_name ?? 'Курс'}: ${som(form.price)} за ученика в месяц с ${formatDate(form.effective_from)}. Предыдущая цена закроется днём раньше и останется в истории.`}
        confirmLabel="Подтвердить"
        isLoading={busy}
        onConfirm={submit}
        onCancel={() => setConfirming(false)}
      />
    </>
  )
}
