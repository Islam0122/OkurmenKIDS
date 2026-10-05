import { useState } from 'react'
import { ArrowRightLeft, GraduationCap, Pencil, UserCheck, UserX } from 'lucide-react'
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
import { Tabs } from '@/components/ui/Tabs'
import { useAssistantFormMutation, useAssistantStudent } from '@/hooks/useAssistant'
import { extractErrorMessage, isNotFound } from '@/lib/apiError'
import type { StudentDetail } from '@/types/assistant'
import { formatDate, formatDateShort } from '@/utils/format'

import { useAssistantActions } from '../actions/AssistantActions'
import { HistoryList } from '../shared'
import { Field, FormError, InfoRow, ModalActions, StudentStatusBadge } from '../ui'

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'schedule', label: 'Расписание' },
  { key: 'attendance', label: 'Посещаемость' },
  { key: 'homework', label: 'Домашние задания' },
  { key: 'exams', label: 'Экзамены' },
  { key: 'scholarships', label: 'Стипендии' },
  { key: 'surveys', label: 'Опросы' },
  { key: 'history', label: 'История' },
] as const
type TabKey = (typeof TABS)[number]['key']

const ATTENDANCE_TONE = { present: 'success', late: 'warning', absent: 'danger', excused: 'info' } as const

function EditContactsModal({ student, onClose }: { student: StudentDetail; onClose: () => void }) {
  const [form, setForm] = useState({
    first_name: student.first_name,
    last_name: student.last_name,
    phone: student.phone,
    parent_phone: student.parent_phone,
    enrollment_date: student.enrollment_date ?? '',
  })
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value })
  const mutation = useAssistantFormMutation(
    () => assistantApi.updateStudent(student.id, { ...form, enrollment_date: form.enrollment_date || null }),
    'Данные студента сохранены',
  )
  return (
    <Modal isOpen onClose={onClose} title="Контакты студента" icon={<Pencil className="size-5 text-brand-600" aria-hidden />}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); mutation.mutate(undefined, { onSuccess: onClose }) }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Имя" htmlFor="contact-first" required><Input id="contact-first" value={form.first_name} onChange={set('first_name')} required /></Field>
          <Field label="Фамилия" htmlFor="contact-last"><Input id="contact-last" value={form.last_name} onChange={set('last_name')} /></Field>
          <Field label="Телефон" htmlFor="contact-phone"><Input id="contact-phone" type="tel" value={form.phone} onChange={set('phone')} /></Field>
          <Field label="Телефон родителя" htmlFor="contact-parent"><Input id="contact-parent" type="tel" value={form.parent_phone} onChange={set('parent_phone')} /></Field>
          <Field label="Дата начала обучения" htmlFor="contact-start"><DatePicker id="contact-start" value={form.enrollment_date} onChange={set('enrollment_date')} /></Field>
        </div>
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={mutation.isPending || !form.first_name.trim()} isLoading={mutation.isPending}>Сохранить</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}

/** The student's central page: who, where, status, and every operational record. */
export function AssistantStudentDetailPage() {
  const { id } = useParams()
  const studentId = Number(id)
  const [params, setParams] = useSearchParams()
  const tab = (TABS.some((t) => t.key === params.get('tab')) ? params.get('tab') : 'overview') as TabKey
  const { data: student, isPending, isError, error, refetch } = useAssistantStudent(Number.isFinite(studentId) ? studentId : undefined)
  const { open } = useAssistantActions()
  const [editing, setEditing] = useState(false)

  if (isPending) return <LoadingState label="Загружаем студента…" />
  if (isError || !student) {
    return isNotFound(error)
      ? <EmptyState icon={GraduationCap} title="Студент не найден" action={<Link to="/assistant/students" className="text-sm font-medium text-brand-700">К списку студентов</Link>} />
      : <ErrorState onRetry={() => void refetch()} />
  }

  const movable = student.status === 'active' || student.status === 'paused'
  const attendancePercent = student.attendance.marked ? Math.round((student.attendance.attended / student.attendance.marked) * 100) : null

  return (
    <div>
      <BackLink to="/assistant/students">Все студенты</BackLink>
      <PageHeader
        title={student.full_name}
        badge={<StudentStatusBadge status={student.status} label={student.status_display} />}
        description={student.group ? <><Link to={`/assistant/groups/${student.group.id}`} className="hover:text-brand-700">{student.group.name}</Link> · {student.course?.name}</> : 'Без группы'}
        actions={
          <>
            {movable ? (
              <Button variant="secondary" leftIcon={<ArrowRightLeft className="size-4" aria-hidden />} onClick={() => open({ type: 'transfer', student })}>Перевести</Button>
            ) : null}
            {student.status === 'active' ? (
              <Button variant="danger" leftIcon={<UserX className="size-4" aria-hidden />} onClick={() => open({ type: 'deactivate', student })}>Деактивировать</Button>
            ) : student.status !== 'completed' ? (
              <Button leftIcon={<UserCheck className="size-4" aria-hidden />} onClick={() => open({ type: 'activate', student })}>Активировать</Button>
            ) : null}
            <Menu items={[{ key: 'edit', label: 'Изменить контакты', icon: <Pencil className="size-4" aria-hidden />, onClick: () => setEditing(true) }]} />
          </>
        }
      />
      <Tabs aria-label="Разделы студента" items={TABS} value={tab} onChange={(key) => setParams(key === 'overview' ? {} : { tab: key }, { replace: true })} />

      {tab === 'overview' ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Обучение">
            <dl className="divide-y divide-border">
              <InfoRow label="Группа">{student.group?.name}</InfoRow>
              <InfoRow label="Программа">{student.course?.name}</InfoRow>
              <InfoRow label="Тренер">{student.teachers.join(', ')}</InfoRow>
              <InfoRow label="Дата начала">{student.enrollment_date ? formatDate(student.enrollment_date) : ''}</InfoRow>
              <InfoRow label="Статус">{student.status_display}</InfoRow>
              <InfoRow label="Посещаемость">{attendancePercent !== null ? `${attendancePercent}% (${student.attendance.attended}/${student.attendance.marked})` : ''}</InfoRow>
            </dl>
          </Card>
          <Card title="Контакты" actions={<Button size="sm" variant="ghost" leftIcon={<Pencil className="size-4" aria-hidden />} onClick={() => setEditing(true)}>Изменить</Button>}>
            <dl className="divide-y divide-border">
              <InfoRow label="Телефон">{student.phone ? <a href={`tel:${student.phone}`} className="hover:text-brand-700">{student.phone}</a> : ''}</InfoRow>
              <InfoRow label="Телефон родителя">{student.parent_phone ? <a href={`tel:${student.parent_phone}`} className="hover:text-brand-700">{student.parent_phone}</a> : ''}</InfoRow>
              <InfoRow label="В системе с">{formatDateShort(student.created_at.slice(0, 10))}</InfoRow>
            </dl>
          </Card>
        </div>
      ) : null}

      {tab === 'schedule' ? (
        <Card title="Расписание группы">
          {student.schedule.length === 0 ? <p className="text-sm text-ink-secondary">Расписания нет.</p> : (
            <ul className="divide-y divide-border text-sm">
              {student.schedule.map((slot) => (
                <li key={slot.id} className="flex flex-wrap justify-between gap-2 py-2.5">
                  <span className="font-medium text-ink">{slot.day_label} · {slot.start}–{slot.end}</span>
                  <span className="text-ink-secondary">{slot.subject?.name ?? ''} · {slot.teacher.name}{slot.room ? ` · ${slot.room.name}` : ''}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'attendance' ? (
        <Card title="Посещаемость" description={attendancePercent !== null ? `${attendancePercent}% — ${student.attendance.attended} из ${student.attendance.marked}` : undefined}>
          {student.attendance.records.length === 0 ? <p className="text-sm text-ink-secondary">Отметок пока нет.</p> : (
            <ul className="divide-y divide-border text-sm">
              {student.attendance.records.map((record) => (
                <li key={record.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0"><span className="font-medium text-ink">{formatDate(record.date, false)}</span><span className="text-ink-secondary"> · {record.group}{record.subject ? ` · ${record.subject}` : ''}</span></span>
                  <Badge tone={ATTENDANCE_TONE[record.status]}>{record.status_display}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'homework' ? (
        <Card title="Домашние задания">
          {student.homework.length === 0 ? <p className="text-sm text-ink-secondary">Домашних заданий пока нет.</p> : (
            <ul className="divide-y divide-border text-sm">
              {student.homework.map((hw) => (
                <li key={hw.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0"><span className="block truncate font-medium text-ink">{hw.title}</span><span className="text-ink-secondary">{formatDate(hw.date, false)}{hw.subject ? ` · ${hw.subject}` : ''}</span></span>
                  <span className="shrink-0 text-right text-ink-secondary">{hw.status_display}{hw.score !== null ? ` · ${hw.score}` : ''}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'exams' ? (
        <Card title="Экзамены">
          {student.exams.length === 0 ? <p className="text-sm text-ink-secondary">Завершённых тестов нет.</p> : (
            <ul className="divide-y divide-border text-sm">
              {student.exams.map((exam) => (
                <li key={exam.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0"><span className="block truncate font-medium text-ink">{exam.title}</span><span className="text-ink-secondary">{exam.subject}{exam.finished_at ? ` · ${formatDateShort(exam.finished_at.slice(0, 10))}` : ''}</span></span>
                  <span className="shrink-0 font-semibold text-ink">{exam.score}%</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'scholarships' ? (
        <Card title="История стипендий">
          {student.scholarships.length === 0 ? <p className="text-sm text-ink-secondary">Стипендий не было.</p> : (
            <ul className="divide-y divide-border text-sm">
              {student.scholarships.map((award) => (
                <li key={award.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <span><span className="font-medium text-ink">{formatDateShort(award.period_start)} – {formatDateShort(award.period_end)}</span><span className="text-ink-secondary"> · место {award.rank} · {award.amount} сом</span></span>
                  <span className="flex gap-2"><Badge tone={award.status === 'approved' ? 'success' : 'warning'}>{award.status_display}</Badge><Badge tone={award.payment_status === 'paid' ? 'success' : 'muted'}>{award.payment_status_display}</Badge></span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'surveys' ? (
        <Card title="Опросы группы">
          {student.surveys.length === 0 ? <p className="text-sm text-ink-secondary">Опросов для группы студента нет.</p> : (
            <ul className="divide-y divide-border text-sm">
              {student.surveys.map((survey) => (
                <li key={survey.id}><Link to={`/assistant/surveys/${survey.id}`} className="flex justify-between gap-3 py-2.5 hover:text-brand-700"><span className="font-medium">{survey.title}</span><span className="text-ink-secondary">{survey.status_display}</span></Link></li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}

      {tab === 'history' ? <Card title="История"><HistoryList rows={student.history} /></Card> : null}

      {editing ? <EditContactsModal student={student} onClose={() => setEditing(false)} /> : null}
    </div>
  )
}
