import { useEffect, useMemo, useState } from 'react'
import { CalendarPlus } from 'lucide-react'

import { assistantApi } from '@/api/assistant'
import { Button } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useAssistantGroup, useAssistantFormMutation, useAssistantOptions } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { Ref, SlotInput } from '@/types/assistant'

import { Field, FormError, ModalActions } from '../ui'
import { SlotsEditor } from './SlotsEditor'

const NEW = 'new'

/**
 * «+ Расписание»: a group's teaching program (trainer + subject) and its
 * exact weekly slots. Saved by the backend's «Учебная конфигурация» service,
 * which refuses any slot clashing with the trainer's, the room's or the
 * group's other slots — the clash comes back named and the modal stays open.
 */
export function ScheduleModal({ group: presetGroup, programId, preset, onClose }: {
  group?: Ref
  programId?: number
  /** A new slot to add (a free spot clicked on the schedule board). */
  preset?: SlotInput
  onClose: () => void
}) {
  const { showToast } = useToast()
  const { data: options } = useAssistantOptions()
  const [groupId, setGroupId] = useState(presetGroup ? String(presetGroup.id) : '')
  const { data: group, isPending: groupLoading } = useAssistantGroup(groupId ? Number(groupId) : undefined)
  const [program, setProgram] = useState<string>(programId ? String(programId) : '')
  const [teacher, setTeacher] = useState('')
  const [subject, setSubject] = useState('')
  const [slots, setSlots] = useState<SlotInput[]>([])
  const [generate, setGenerate] = useState(true)
  // Which group/program the form was last filled from — so a background
  // refetch of the group never overwrites slots being edited.
  const [loadedKey, setLoadedKey] = useState('')

  // Pick the group's first program by default, and load its current slots.
  useEffect(() => {
    if (!group) return
    const chosen = program && program !== NEW
      ? group.programs.find((p) => String(p.id) === program)
      : program === NEW ? undefined : group.programs.find((p) => p.is_active)
    const effective = chosen ? String(chosen.id) : NEW
    const key = `${group.id}:${effective}`
    if (key === loadedKey) return
    setLoadedKey(key)
    setProgram(effective)
    setTeacher(chosen ? String(chosen.teacher.id) : '')
    setSubject(chosen?.subject ? String(chosen.subject.id) : '')
    const current: SlotInput[] = chosen ? chosen.slots.map((s) => ({ id: s.id, day: s.day, start: s.start, end: s.end, room: s.room?.id ?? null })) : []
    const hasPreset = preset && current.some((s) => s.day === preset.day && s.start === preset.start)
    setSlots(preset && !hasPreset ? [...current, { ...preset, id: null }] : current)
  }, [group, program, loadedKey, preset])

  const subjects = useMemo(() => {
    const course = options?.courses.find((c) => c.id === group?.course.id)
    return (course?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name }))
  }, [options, group])
  useEffect(() => {
    if (program === NEW && !subject && subjects.length === 1) setSubject(subjects[0].value)
  }, [program, subject, subjects])

  const teachers = (options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))
  const groups = (options?.groups ?? []).map((g) => ({ value: String(g.id), label: `${g.name} — ${g.course}` }))
  const programs = [
    ...(group?.programs ?? []).map((p) => ({ value: String(p.id), label: `${p.subject?.name ?? 'Без предмета'} — ${p.teacher.name}` })),
    { value: NEW, label: '+ Новая программа (тренер и предмет)' },
  ]

  const mutation = useAssistantFormMutation(async () => {
    const saved = await assistantApi.saveProgram(Number(groupId), {
      program: program && program !== NEW ? Number(program) : null,
      teacher: Number(teacher),
      subject: Number(subject),
      slots,
    })
    if (generate && slots.length) {
      try {
        const report = await assistantApi.generateLessons(Number(groupId))
        if (report.warnings.length) showToast(report.warnings[0], 'info')
      } catch (error) {
        showToast(`Расписание сохранено, но занятия не сгенерированы: ${extractErrorMessage(error)}`, 'error')
      }
    }
    return saved
  }, 'Расписание сохранено')

  const canSubmit = groupId !== '' && teacher !== '' && subject !== '' && slots.every((s) => s.start && s.end)

  return (
    <Modal isOpen onClose={onClose} title={preset ? 'Добавить занятие' : 'Расписание группы'} size="lg" icon={<CalendarPlus className="size-5 text-brand-600" aria-hidden />}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSubmit) mutation.mutate(undefined, { onSuccess: onClose })
        }}
      >
        {preset ? (
          <p className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">
            Слот <strong>{options?.weekdays.find((d) => d.code === preset.day)?.label ?? preset.day} {preset.start}–{preset.end}</strong>
            {preset.room ? <> · кабинет <strong>{options?.rooms.find((r) => r.id === preset.room)?.name}</strong></> : null}{' '}
            добавится в еженедельное расписание выбранной группы, и по нему создадутся занятия.
            Тренер, кабинет и группа проверяются на пересечения при сохранении.
          </p>
        ) : null}
        {!presetGroup ? (
          <Field label="Группа" htmlFor="schedule-group" required>
            <Select id="schedule-group" value={groupId} onChange={(event) => { setGroupId(event.target.value); setProgram('') }} options={groups} placeholder="Выберите группу" />
          </Field>
        ) : null}
        {groupId && groupLoading ? <LoadingState label="Загружаем расписание группы…" /> : null}
        {group ? (
          <>
            <Field label="Программа" htmlFor="schedule-program">
              <Select id="schedule-program" value={program} onChange={(event) => setProgram(event.target.value)} options={programs} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Тренер" htmlFor="schedule-teacher" required>
                <Select id="schedule-teacher" value={teacher} onChange={(event) => setTeacher(event.target.value)} options={teachers} placeholder="Выберите тренера" />
              </Field>
              <Field label="Предмет" htmlFor="schedule-subject" required>
                <Select id="schedule-subject" value={subject} onChange={(event) => setSubject(event.target.value)} options={subjects} placeholder="Выберите предмет" />
              </Field>
            </div>
            <Field label="Дни и время">
              <SlotsEditor slots={slots} onChange={setSlots} />
            </Field>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="size-4 accent-brand-500" checked={generate} onChange={(event) => setGenerate(event.target.checked)} />
              Сразу обновить занятия группы по новому расписанию
            </label>
          </>
        ) : null}
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending}>Сохранить расписание</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}
