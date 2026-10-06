import { useMemo, useState } from 'react'
import { Settings2, Users } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { Button } from '@/components/ui/Button'
import { DatePicker } from '@/components/ui/DatePicker'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useAssistantFormMutation, useAssistantOptions, useAssistantStudents } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { DayOfWeek } from '@/types/common'
import { cn } from '@/utils/cn'

import { Field, FormError, ModalActions, todayIso } from '../ui'

/**
 * «+ Группа», быстрый режим: одна форма — название, программа, тренер,
 * дата начала, дни и время, студенты. Everything else (end date, limit,
 * several programs, room per day, lesson generation off) lives in the full
 * wizard behind «Расширенные настройки». Saved by the same backend service.
 */
export function QuickGroupModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { data: options } = useAssistantOptions()
  const [name, setName] = useState('')
  const [course, setCourse] = useState('')
  const [teacher, setTeacher] = useState('')
  const [subject, setSubject] = useState('')
  const [startDate, setStartDate] = useState(todayIso())
  const [days, setDays] = useState<DayOfWeek[]>(['mon', 'wed', 'fri'])
  const [start, setStart] = useState('16:00')
  const [end, setEnd] = useState('17:30')
  const [room, setRoom] = useState('')
  const [search, setSearch] = useState('')
  const [students, setStudents] = useState<Set<number>>(new Set())
  const { data: page, isPending: studentsLoading } = useAssistantStudents({ search: search || undefined, status: 'active', page_size: 30 })

  const selectedCourse = options?.courses.find((c) => String(c.id) === course)
  const subjects = useMemo(() => (selectedCourse?.subjects ?? []).map((s) => ({ value: String(s.id), label: s.name })), [selectedCourse])
  const effectiveSubject = subject || (subjects.length === 1 ? subjects[0].value : '')
  // Trainers who teach one of the course's subjects first; the rest after.
  const teachers = useMemo(() => {
    const courseSubjects = new Set(selectedCourse?.subjects.map((s) => s.id) ?? [])
    return [...(options?.teachers ?? [])]
      .sort((a, b) => Number(b.subjects.some((s) => courseSubjects.has(s))) - Number(a.subjects.some((s) => courseSubjects.has(s))))
      .map((t) => ({ value: String(t.id), label: t.name }))
  }, [options, selectedCourse])

  const withProgram = teacher !== ''
  const mutation = useAssistantFormMutation(
    () => assistantApi.createGroup({
      name: name.trim(),
      course: Number(course),
      start_date: startDate,
      programs: withProgram
        ? [{ teacher: Number(teacher), subject: Number(effectiveSubject), slots: days.map((day) => ({ day, start, end, room: room ? Number(room) : null })) }]
        : [],
      students: [...students],
      generate_lessons: withProgram && days.length > 0,
    }),
    (group) => (group.generation ? `Группа ${group.name} создана, занятий: ${group.generation.created}` : `Группа ${group.name} создана`),
  )
  const canSubmit = name.trim() !== '' && course !== '' && startDate !== '' &&
    (!withProgram || (effectiveSubject !== '' && days.length > 0 && start !== '' && end > start))

  const toggleDay = (day: DayOfWeek) => setDays((current) => (current.includes(day) ? current.filter((d) => d !== day) : [...current, day]))
  const toggleStudent = (id: number) => setStudents((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  return (
    <Modal isOpen onClose={onClose} title="Новая группа" size="lg" icon={<Users className="size-5 text-brand-600" aria-hidden />}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSubmit) mutation.mutate(undefined, { onSuccess: (group) => { onClose(); navigate(`/assistant/groups/${group.id}`) } })
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Название группы" htmlFor="qg-name" required>
            <Input id="qg-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="PRO-05" autoFocus maxLength={150} />
          </Field>
          <Field label="Программа" htmlFor="qg-course" required>
            <Select id="qg-course" value={course} onChange={(e) => { setCourse(e.target.value); setSubject('') }} placeholder="Выберите программу"
              options={(options?.courses ?? []).map((c) => ({ value: String(c.id), label: c.name }))} />
          </Field>
          <Field label="Тренер" htmlFor="qg-teacher" hint={withProgram ? undefined : 'Можно назначить позже.'}>
            <Select id="qg-teacher" value={teacher} onChange={(e) => setTeacher(e.target.value)} placeholder="Назначить позже" options={teachers} />
          </Field>
          <Field label="Дата начала" htmlFor="qg-start" required>
            <DatePicker id="qg-start" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          {withProgram && subjects.length > 1 ? (
            <Field label="Предмет тренера" htmlFor="qg-subject" required className="sm:col-span-2">
              <Select id="qg-subject" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Выберите предмет" options={subjects} />
            </Field>
          ) : null}
        </div>

        {withProgram ? (
          <fieldset className="rounded-lg border border-border p-3">
            <legend className="px-1 text-sm font-medium text-ink">Расписание</legend>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Дни занятий">
              {(options?.weekdays ?? []).map((day) => (
                <button key={day.code} type="button" aria-pressed={days.includes(day.code)} onClick={() => toggleDay(day.code)}
                  className={cn('h-9 min-w-11 rounded-lg border px-2 text-sm font-medium transition-colors',
                    days.includes(day.code) ? 'border-brand-500 bg-brand-500 text-white' : 'border-border text-ink-secondary hover:bg-surface-hover')}>
                  {day.short}
                </button>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Input aria-label="Начало" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
              <Input aria-label="Окончание" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
              <Select aria-label="Аудитория" value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Без аудитории" className="col-span-2 sm:col-span-1"
                options={(options?.rooms ?? []).map((r) => ({ value: String(r.id), label: r.name }))} />
            </div>
          </fieldset>
        ) : null}

        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-ink">Студенты</span>
            <span className="text-xs text-ink-secondary">Выбрано: {students.size}</span>
          </div>
          <SearchInput value={search} onChange={setSearch} placeholder="Поиск студента…" />
          <ul className="mt-2 max-h-44 divide-y divide-border overflow-y-auto rounded-lg border border-border">
            {studentsLoading ? <li><LoadingState label="Ищем…" /></li> : null}
            {page?.results.map((student) => (
              <li key={student.id}>
                <label className="flex cursor-pointer items-center gap-3 px-3 py-1.5 text-sm hover:bg-surface-hover">
                  <input type="checkbox" className="size-4 accent-brand-500" checked={students.has(student.id)} onChange={() => toggleStudent(student.id)} />
                  <span className="min-w-0 flex-1 truncate text-ink">{student.full_name}</span>
                  <span className="shrink-0 text-xs text-ink-muted">{student.group?.name ?? 'без группы'}</span>
                </label>
              </li>
            ))}
            {page && page.results.length === 0 ? <li className="p-3 text-center text-sm text-ink-secondary">Никого не нашли.</li> : null}
          </ul>
        </div>

        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Link to="/assistant/groups/create" onClick={onClose}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg px-3 text-sm font-medium text-ink-secondary hover:bg-surface-hover sm:mr-auto">
            <Settings2 className="size-4" aria-hidden />Расширенные настройки
          </Link>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending}>Создать группу</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}
