import { useState } from 'react'
import { ArrowRightLeft, CalendarDays, CalendarPlus, Pencil, RefreshCw, UserCheck, UserPlus, Users, UserX } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Menu } from '@/components/ui/Menu'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { Tabs } from '@/components/ui/Tabs'
import { Textarea } from '@/components/ui/Textarea'
import { useAssistantGroup, useAssistantFormMutation, useAssistantMutation, useAssistantOptions } from '@/hooks/useAssistant'
import { extractErrorMessage, isNotFound } from '@/lib/apiError'
import type { GroupDetail, StudentRow } from '@/types/assistant'
import { formatDate, formatDateShort, pluralize } from '@/utils/format'

import { useAssistantActions } from '../actions/AssistantActions'
import { GroupAttendanceTab, GroupHomeworkTab } from '../records/GroupRecordTabs'
import { HistoryList, LessonList } from '../shared'
import { Field, FormError, GroupStatusBadge, InfoRow, ModalActions, StudentStatusBadge } from '../ui'

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'students', label: 'Студенты' },
  { key: 'schedule', label: 'Расписание' },
  { key: 'attendance', label: 'Посещаемость' },
  { key: 'homework', label: 'ДЗ' },
  { key: 'lessons', label: 'Занятия' },
  { key: 'exams', label: 'Экзамены' },
  { key: 'surveys', label: 'Опросы' },
  { key: 'history', label: 'История' },
] as const
type TabKey = (typeof TABS)[number]['key']

function EditGroupModal({ group, onClose }: { group: GroupDetail; onClose: () => void }) {
  const { data: options } = useAssistantOptions()
  const [form, setForm] = useState({
    name: group.name,
    start_date: group.start_date,
    end_date: group.end_date ?? '',
    max_students: group.max_students ? String(group.max_students) : '',
    status: group.status,
    description: group.description,
  })
  const mutation = useAssistantFormMutation(
    () => assistantApi.updateGroup(group.id, {
      ...form,
      end_date: form.end_date || null,
      max_students: form.max_students ? Number(form.max_students) : null,
    }),
    'Группа сохранена',
  )
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value })

  return (
    <Modal isOpen onClose={onClose} title="Изменить группу" icon={<Pencil className="size-5 text-brand-600" aria-hidden />}>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(undefined, { onSuccess: onClose }) }}>
        <Field label="Название" htmlFor="edit-name" required>
          <Input id="edit-name" value={form.name} onChange={set('name')} required />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Дата начала" htmlFor="edit-start" required>
            <DatePicker id="edit-start" value={form.start_date} onChange={set('start_date')} required />
          </Field>
          <Field label="Дата окончания" htmlFor="edit-end">
            <DatePicker id="edit-end" value={form.end_date} onChange={set('end_date')} />
          </Field>
          <Field label="Максимум студентов" htmlFor="edit-max">
            <Input id="edit-max" type="number" min={1} value={form.max_students} onChange={set('max_students')} />
          </Field>
          <Field label="Статус" htmlFor="edit-status">
            <Select id="edit-status" value={form.status} onChange={set('status')} options={(options?.group_statuses ?? []).map((s) => ({ value: s.value, label: s.label }))} />
          </Field>
        </div>
        <Field label="Описание" htmlFor="edit-description">
          <Textarea id="edit-description" rows={3} value={form.description} onChange={set('description')} />
        </Field>
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={mutation.isPending || !form.name.trim()} isLoading={mutation.isPending}>Сохранить</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}

function GroupStudents({ group }: { group: GroupDetail }) {
  const { open } = useAssistantActions()
  const [search, setSearch] = useState('')
  const ref = { id: group.id, name: group.name }
  const q = search.trim().toLowerCase()
  const students = q ? group.students.filter((s) => s.full_name.toLowerCase().includes(q) || s.phone.includes(q)) : group.students
  return (
    <Card title={`Студенты (${group.students.length})`} actions={
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => open({ type: 'bulk', action: 'add_to_group', group: ref })}>Добавить существующих</Button>
        <Button size="sm" leftIcon={<UserPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'create-student', group: ref })}>Новый</Button>
      </div>
    }>
      {group.students.length > 5 ? <div className="mb-3 max-w-xs"><SearchInput value={search} onChange={setSearch} placeholder="Поиск в группе…" /></div> : null}
      <StudentsTable students={students} />
    </Card>
  )
}

function StudentsTable({ students }: { students: StudentRow[] }) {
  const { open } = useAssistantActions()
  if (students.length === 0) return <EmptyState icon={Users} title="В группе нет студентов" className="py-6" />
  return (
    <div className="-mx-4 overflow-x-auto sm:-mx-5">
      <table className="data-table min-w-[640px]">
        <thead>
          <tr><th>Студент</th><th>Телефон</th><th>Статус</th><th>Посещаемость</th><th className="text-right">Действия</th></tr>
        </thead>
        <tbody>
          {students.map((student) => (
            <tr key={student.id}>
              <td><Link to={`/assistant/students/${student.id}`} className="font-medium text-ink hover:text-brand-700">{student.full_name}</Link></td>
              <td className="text-ink-secondary">{student.phone || student.parent_phone || '—'}</td>
              <td><StudentStatusBadge status={student.status} label={student.status_display} /></td>
              <td>{student.attendance_percent !== null ? `${student.attendance_percent}%` : '—'}</td>
              <td className="text-right">
                <Menu
                  label={`Действия: ${student.full_name}`}
                  items={[
                    { key: 'transfer', label: 'Перевести', icon: <ArrowRightLeft className="size-4" aria-hidden />, onClick: () => open({ type: 'transfer', student }), disabled: !['active', 'paused'].includes(student.status) },
                    student.status === 'active'
                      ? { key: 'deactivate', label: 'Деактивировать', tone: 'danger' as const, icon: <UserX className="size-4" aria-hidden />, onClick: () => open({ type: 'deactivate', student }) }
                      : { key: 'activate', label: 'Активировать', icon: <UserCheck className="size-4" aria-hidden />, onClick: () => open({ type: 'activate', student }), disabled: student.status === 'completed' },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AssistantGroupDetailPage() {
  const { id } = useParams()
  const groupId = Number(id)
  const [params, setParams] = useSearchParams()
  const tab = (TABS.some((t) => t.key === params.get('tab')) ? params.get('tab') : 'overview') as TabKey
  const { data: group, isPending, isError, error, refetch } = useAssistantGroup(Number.isFinite(groupId) ? groupId : undefined)
  const { open } = useAssistantActions()
  const [editing, setEditing] = useState(false)
  const generate = useAssistantMutation(() => assistantApi.generateLessons(groupId), (report) =>
    report.created ? `Создано занятий: ${report.created}` : 'Занятия уже актуальны')

  if (isPending) return <LoadingState label="Загружаем группу…" />
  if (isError || !group) {
    return isNotFound(error)
      ? <EmptyState icon={Users} title="Группа не найдена" action={<Link to="/assistant/groups" className="text-sm font-medium text-brand-700">К списку групп</Link>} />
      : <ErrorState onRetry={() => void refetch()} />
  }

  const ref = { id: group.id, name: group.name }
  return (
    <div>
      <BackLink to="/assistant/groups">Все группы</BackLink>
      <PageHeader
        title={group.name}
        badge={<GroupStatusBadge status={group.status} label={group.status_display} />}
        description={
          <>
            {group.course.name} · Тренер: {group.teachers.length ? group.teachers.join(', ') : 'не назначен'} · {group.students_count}{' '}
            {pluralize(group.students_count, 'активный студент', 'активных студента', 'активных студентов')}
            {group.schedule ? <span className="block">{group.schedule}</span> : null}
          </>
        }
        actions={
          <>
            <Button leftIcon={<UserPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'create-student', group: ref })}>Студент</Button>
            <Button variant="secondary" leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'schedule', group: ref })}>Расписание</Button>
            <Button variant="secondary" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={() => setEditing(true)}>Изменить</Button>
            <Menu
              items={[
                { key: 'existing', label: 'Добавить существующих студентов', icon: <UserPlus className="size-4" aria-hidden />, onClick: () => open({ type: 'bulk', action: 'add_to_group', group: ref }) },
                { key: 'generate', label: 'Сгенерировать занятия', icon: <RefreshCw className="size-4" aria-hidden />, onClick: () => generate.mutate(undefined), disabled: generate.isPending || group.programs.length === 0 },
              ]}
            />
          </>
        }
      />
      <Tabs aria-label="Разделы группы" items={TABS} value={tab} onChange={(key) => setParams(key === 'overview' ? {} : { tab: key }, { replace: true })} />

      {tab === 'overview' ? (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Card title="Информация о группе">
            <dl className="-my-2 divide-y divide-border">
              <InfoRow label="Программа">{group.course.name}</InfoRow>
              <InfoRow label="Тренер">{group.teachers.join(', ')}</InfoRow>
              <InfoRow label="Начало">{formatDateShort(group.start_date)}</InfoRow>
              {group.end_date ? <InfoRow label="Окончание">{formatDateShort(group.end_date)}</InfoRow> : null}
              <InfoRow label="Студенты">{`${group.students_count}${group.max_students ? ` из ${group.max_students}` : ''}`}</InfoRow>
              <InfoRow label="Расписание">{group.schedule}</InfoRow>
              <InfoRow label="Статус">{group.status_display}</InfoRow>
              <InfoRow label="Занятий">{String(group.lessons_total)}</InfoRow>
            </dl>
            {group.description ? <p className="mt-3 text-sm text-ink-secondary">{group.description}</p> : null}
          </Card>
          <Card title="Занятия">
            {[['Сегодня', group.today_lesson], ['Следующее', group.next_lesson]].map(([label, lesson]) => (
              <div key={label as string} className="mb-2 last:mb-0">
                <p className="field-label mb-1">{label as string}</p>
                {lesson && typeof lesson === 'object' ? (
                  <button type="button" onClick={() => open({ type: 'lesson', lesson })}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-left text-sm hover:border-brand-200 hover:bg-brand-50/40">
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">{formatDate(lesson.date, false)} · {lesson.start}–{lesson.end}</span>
                      <span className="block truncate text-ink-secondary">№{lesson.lesson_number} {lesson.topic || lesson.subject?.name} · {lesson.teacher?.name ?? '—'}</span>
                    </span>
                    <span className="shrink-0 text-xs text-ink-muted">{lesson.status_display}</span>
                  </button>
                ) : <p className="text-sm text-ink-secondary">—</p>}
              </div>
            ))}
            <p className="field-label mt-3 mb-1">Далее</p>
            <LessonList lessons={group.upcoming_lessons.filter((l) => l.id !== group.today_lesson?.id && l.id !== group.next_lesson?.id).slice(0, 4)} empty="Больше запланированных занятий нет." />
          </Card>
          <Card title="Недавняя посещаемость" actions={<button type="button" onClick={() => setParams({ tab: 'attendance' }, { replace: true })} className="text-sm font-medium text-brand-700 hover:underline">Подробнее</button>}>
            {group.recent_attendance.length === 0 ? <p className="text-sm text-ink-secondary">Прошедших занятий нет.</p> : (
              <ul className="divide-y divide-border text-sm">
                {group.recent_attendance.map((lesson) => (
                  <li key={lesson.id} onClick={() => open({ type: 'lesson-detail', lessonId: lesson.id })} className="flex cursor-pointer items-center justify-between gap-3 py-2 hover:bg-surface-hover">
                    <span className="min-w-0 truncate"><span className="font-medium text-ink">{formatDateShort(lesson.date)}</span><span className="text-ink-secondary"> · {lesson.subject?.name ?? ''}</span></span>
                    {lesson.marked ? (
                      <span className="shrink-0 tabular-nums text-ink">{lesson.attended}/{lesson.marked}
                        <span className="ml-1.5 text-ink-secondary">{Math.round((lesson.attended / lesson.marked) * 100)}%</span></span>
                    ) : <span className="shrink-0 text-warning">не отмечено</span>}
                  </li>
                ))}
              </ul>
            )}
            {group.attendance.percent !== null ? <p className="mt-3 text-xs text-ink-secondary">За всё время: {group.attendance.percent}% ({group.attendance.attended}/{group.attendance.marked})</p> : null}
          </Card>
        </div>
      ) : null}

      {tab === 'students' ? <GroupStudents group={group} /> : null}

      {tab === 'schedule' ? (
        group.programs.length === 0 ? (
          <EmptyState icon={CalendarDays} title="Расписания пока нет" description="Назначьте тренера и дни занятий."
            action={<Button leftIcon={<CalendarPlus className="size-4" aria-hidden />} onClick={() => open({ type: 'schedule', group: ref })}>Добавить расписание</Button>} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {group.programs.map((program) => (
              <Card key={program.id} title={program.subject?.name ?? 'Без предмета'} description={`Тренер: ${program.teacher.name}`}
                actions={<Button size="sm" variant="secondary" onClick={() => open({ type: 'schedule', group: ref, programId: program.id })}>Изменить</Button>}>
                {!program.is_active ? <Badge tone="muted">Неактивна</Badge> : null}
                {program.slots.length === 0 ? <p className="text-sm text-ink-secondary">Дни не назначены.</p> : (
                  <ul className="divide-y divide-border text-sm">
                    {program.slots.map((slot) => (
                      <li key={slot.id} className="flex justify-between gap-3 py-2">
                        <span className="font-medium text-ink">{slot.day_label}</span>
                        <span className="text-ink-secondary">{slot.start}–{slot.end}{slot.room ? ` · ${slot.room.name}` : ''}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
          </div>
        )
      ) : null}

      {tab === 'attendance' ? <GroupAttendanceTab group={group} /> : null}
      {tab === 'homework' ? <GroupHomeworkTab group={group} /> : null}

      {tab === 'lessons' ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Прошедшие"><LessonList lessons={group.recent_lessons} empty="Прошедших занятий нет." onOpen={(id) => open({ type: 'lesson-detail', lessonId: id })} /></Card>
          <Card title="Предстоящие"><LessonList lessons={group.upcoming_lessons} empty="Нет запланированных занятий." onOpen={(id) => open({ type: 'lesson-detail', lessonId: id })} /></Card>
        </div>
      ) : null}

      {tab === 'exams' ? (
        <Card title="Экзамены и тесты">
          {group.exams.length === 0 ? <p className="text-sm text-ink-secondary">Тестовых сессий у группы не было.</p> : (
            <ul className="divide-y divide-border text-sm">
              {group.exams.map((exam) => (
                <li key={exam.id} className="flex justify-between gap-3 py-2.5">
                  <span className="font-medium text-ink">{exam.title || 'Тест'}</span>
                  <span className="text-ink-secondary">{exam.status_display} · {formatDateShort(exam.created_at.slice(0, 10))}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'surveys' ? (
        <Card title="Опросы" actions={<Link to={`/assistant/surveys?create=1&group=${group.id}`} className="text-sm font-medium text-brand-700 hover:underline">Создать опрос</Link>}>
          {group.surveys.length === 0 ? <p className="text-sm text-ink-secondary">Опросов для группы нет.</p> : (
            <ul className="divide-y divide-border text-sm">
              {group.surveys.map((survey) => (
                <li key={survey.id}>
                  <Link to={`/assistant/surveys/${survey.id}`} className="flex justify-between gap-3 py-2.5 hover:text-brand-700">
                    <span className="font-medium">{survey.title}</span>
                    <span className="text-ink-secondary">{survey.status_display}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'history' ? <Card title="История"><HistoryList rows={group.history} /></Card> : null}

      {editing ? <EditGroupModal group={group} onClose={() => setEditing(false)} /> : null}
    </div>
  )
}
