import { useMemo, useState } from 'react'
import { Check, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantOptions, useAssistantStudents } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { SlotInput, StudentRow } from '@/types/assistant'
import { cn } from '@/utils/cn'

import { SlotsEditor } from '../actions/SlotsEditor'
import { Field, FormError, StudentStatusBadge, todayIso } from '../ui'

const STEPS = ['Основное', 'Тренер', 'Расписание', 'Студенты', 'Проверка'] as const

const DEFAULT_SLOTS: SlotInput[] = [
  { day: 'mon', start: '16:00', end: '17:30', room: null },
  { day: 'wed', start: '16:00', end: '17:30', room: null },
  { day: 'fri', start: '16:00', end: '17:30', room: null },
]

function Stepper({ step, onJump }: { step: number; onJump: (index: number) => void }) {
  return (
    <ol className="scroll-x mb-6 flex gap-2">
      {STEPS.map((label, index) => {
        const done = index < step
        const current = index === step
        return (
          <li key={label} className="shrink-0">
            <button
              type="button"
              disabled={index > step}
              onClick={() => onJump(index)}
              aria-current={current ? 'step' : undefined}
              className={cn(
                'flex h-9 items-center gap-2 rounded-full border px-3 text-sm font-medium',
                current ? 'border-brand-500 bg-brand-50 text-brand-700' : done ? 'border-brand-200 text-brand-700 hover:bg-brand-50' : 'border-border text-ink-muted',
              )}
            >
              <span className={cn('flex size-5 items-center justify-center rounded-full text-xs', current || done ? 'bg-brand-500 text-white' : 'bg-surface-hover text-ink-muted')}>
                {done ? <Check className="size-3" aria-hidden /> : index + 1}
              </span>
              {label}
            </button>
          </li>
        )
      })}
    </ol>
  )
}

/** «Создать группу»: основное → тренер → расписание → студенты → проверка. One transaction on the backend. */
export function AssistantGroupCreatePage() {
  const navigate = useNavigate()
  const { data: options, isPending } = useAssistantOptions()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [course, setCourse] = useState('')
  const [startDate, setStartDate] = useState(todayIso())
  const [endDate, setEndDate] = useState('')
  const [maxStudents, setMaxStudents] = useState('')
  const [teacher, setTeacher] = useState('')
  const [subject, setSubject] = useState('')
  const [slots, setSlots] = useState<SlotInput[]>(DEFAULT_SLOTS)
  const [students, setStudents] = useState<Map<number, StudentRow>>(new Map())
  const [studentSearch, setStudentSearch] = useState('')
  const [generate, setGenerate] = useState(true)

  const selectedCourse = options?.courses.find((c) => String(c.id) === course)
  const subjects = useMemo(() => (selectedCourse?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name })), [selectedCourse])
  const teacherName = options?.teachers.find((t) => String(t.id) === teacher)?.name
  const subjectName = selectedCourse?.subjects.find((s) => String(s.id) === subject)?.name
  const withProgram = teacher !== '' && subject !== ''
  const { data: studentPage, isPending: studentsLoading } = useAssistantStudents(
    { search: studentSearch || undefined, status: 'active', page_size: 30 },
    step === 3,
  )

  const mutation = useAssistantFormMutation(
    () => assistantApi.createGroup({
      name: name.trim(),
      course: Number(course),
      start_date: startDate,
      end_date: endDate || null,
      max_students: maxStudents ? Number(maxStudents) : null,
      programs: withProgram ? [{ teacher: Number(teacher), subject: Number(subject), slots }] : [],
      students: [...students.keys()],
      generate_lessons: generate && withProgram && slots.length > 0,
    }),
    (group) => (group.generation ? `Группа ${group.name} создана, занятий: ${group.generation.created}` : `Группа ${group.name} создана`),
  )

  const stepValid = [
    name.trim() !== '' && course !== '' && startDate !== '' && (!endDate || endDate >= startDate),
    (teacher === '') === (subject === ''),
    !withProgram || slots.every((s) => s.start && s.end && s.end > s.start),
    true,
    true,
  ]

  const pickCourse = (value: string) => {
    setCourse(value)
    const next = options?.courses.find((c) => String(c.id) === value)
    setSubject(next && next.subjects.length === 1 ? String(next.subjects[0].id) : '')
  }

  const toggleStudent = (student: StudentRow) =>
    setStudents((current) => {
      const next = new Map(current)
      if (next.has(student.id)) next.delete(student.id)
      else next.set(student.id, student)
      return next
    })

  if (isPending) return <LoadingState label="Загружаем справочники…" />

  const scheduleLabel = slots.length
    ? slots.map((s) => `${options?.weekdays.find((d) => d.code === s.day)?.short ?? s.day} ${s.start}–${s.end}`).join(', ')
    : '—'

  return (
    <div className="mx-auto max-w-3xl">
      <BackLink to="/assistant/groups">К списку групп</BackLink>
      <PageHeader title="Создать группу" description="Пять коротких шагов — группа сразу готова к занятиям." />
      <Stepper step={step} onJump={setStep} />

      <Card>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (!stepValid[step]) return
            if (step < STEPS.length - 1) setStep(step + 1)
            else mutation.mutate(undefined, { onSuccess: (group) => navigate(`/assistant/groups/${group.id}`) })
          }}
          className="space-y-4"
        >
          {step === 0 ? (
            <>
              <Field label="Название группы" htmlFor="group-name" required hint="Например: PRO-01">
                <Input id="group-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={150} />
              </Field>
              <Field label="Программа (курс)" htmlFor="group-course" required>
                <Select id="group-course" value={course} onChange={(e) => pickCourse(e.target.value)} placeholder="Выберите курс"
                  options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: `${c.name} · ${c.count_lesson} занятий` }))} />
              </Field>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Дата начала" htmlFor="group-start" required>
                  <DatePicker id="group-start" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                </Field>
                <Field label="Дата окончания" htmlFor="group-end" error={endDate && endDate < startDate ? 'Раньше даты начала' : null}>
                  <DatePicker id="group-end" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} />
                </Field>
                <Field label="Максимум студентов" htmlFor="group-max">
                  <Input id="group-max" type="number" min={1} value={maxStudents} onChange={(e) => setMaxStudents(e.target.value)} />
                </Field>
              </div>
            </>
          ) : null}

          {step === 1 ? (
            <>
              <Field label="Тренер" htmlFor="group-teacher" hint="Можно назначить позже — тогда шаг расписания пропускается.">
                <Select id="group-teacher" value={teacher} onChange={(e) => setTeacher(e.target.value)} placeholder="Назначить позже"
                  options={(options?.teachers ?? []).map((t) => ({ value: String(t.id), label: t.name }))} />
              </Field>
              <Field label="Предмет" htmlFor="group-subject" required={teacher !== ''}
                error={teacher !== '' && subject === '' ? 'Выберите предмет, который ведёт тренер' : null}>
                <Select id="group-subject" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Выберите предмет" options={subjects} />
              </Field>
            </>
          ) : null}

          {step === 2 ? (
            withProgram ? (
              <Field label={`Дни и время — ${teacherName ?? ''}`}>
                <SlotsEditor slots={slots} onChange={setSlots} />
              </Field>
            ) : (
              <p className="text-sm text-ink-secondary">Тренер не выбран — расписание можно добавить позже на странице группы.</p>
            )
          ) : null}

          {step === 3 ? (
            <>
              <SearchInput value={studentSearch} onChange={setStudentSearch} placeholder="Поиск студента…" />
              <p className="text-sm text-ink-secondary">Выбрано: <b className="text-ink">{students.size}</b>. Студент из другой группы будет переведён (с записью в истории).</p>
              <div className="max-h-96 overflow-y-auto rounded-lg border border-border">
                {studentsLoading ? <LoadingState label="Ищем студентов…" /> : null}
                {studentPage && studentPage.results.length === 0 ? <p className="p-4 text-center text-sm text-ink-secondary">Студенты не найдены.</p> : null}
                <ul className="divide-y divide-border">
                  {studentPage?.results.map((student) => (
                    <li key={student.id}>
                      <label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 hover:bg-surface-hover">
                        <input type="checkbox" className="size-4 accent-brand-500" checked={students.has(student.id)} onChange={() => toggleStudent(student)} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-ink">{student.full_name}</span>
                          <span className="block truncate text-xs text-ink-secondary">{student.group?.name ?? 'Без группы'}</span>
                        </span>
                        <StudentStatusBadge status={student.status} label={student.status_display} />
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          ) : null}

          {step === 4 ? (
            <>
              <dl className="divide-y divide-border rounded-lg border border-border px-4">
                {[
                  ['Группа', name],
                  ['Программа', selectedCourse?.name],
                  ['Тренер', withProgram ? `${teacherName} (${subjectName})` : 'назначить позже'],
                  ['Студенты', String(students.size)],
                  ['Расписание', withProgram ? scheduleLabel : '—'],
                  ['Начало', startDate],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4 py-2.5 text-sm">
                    <dt className="text-ink-secondary">{label}</dt>
                    <dd className="text-right font-medium text-ink">{value}</dd>
                  </div>
                ))}
              </dl>
              {withProgram && slots.length ? (
                <label className="flex items-center gap-2 text-sm text-ink">
                  <input type="checkbox" className="size-4 accent-brand-500" checked={generate} onChange={(e) => setGenerate(e.target.checked)} />
                  Сразу сгенерировать занятия по плану курса
                </label>
              ) : null}
            </>
          ) : null}

          <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />

          <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-between">
            <Button type="button" variant="secondary" onClick={() => (step === 0 ? navigate('/assistant/groups') : setStep(step - 1))}>
              {step === 0 ? 'Отмена' : 'Назад'}
            </Button>
            <Button type="submit" disabled={!stepValid[step] || mutation.isPending} isLoading={mutation.isPending}
              leftIcon={step === STEPS.length - 1 ? <Users className="size-4" aria-hidden /> : undefined}>
              {step === STEPS.length - 1 ? 'Создать группу' : 'Далее'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
