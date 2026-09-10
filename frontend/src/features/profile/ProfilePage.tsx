import { Briefcase, Calendar, Mail, Phone, User as UserIcon } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { formatDate, pluralize } from '@/utils/format'

import { useTeacherProfile } from './useTeacherProfile'

export function ProfilePage() {
  const { data: teacher, isPending, isError, refetch } = useTeacherProfile()

  if (isPending) return <LoadingState label="Загружаем профиль…" />
  if (isError || !teacher) return <ErrorState onRetry={() => void refetch()} />

  const fullName = `${teacher.user.last_name} ${teacher.user.first_name}`.trim() || teacher.user.username

  return (
    <div>
      <PageHeader title="Профиль" description="Данные вашего профиля — доступны только для просмотра." />

      <div className="rounded-xl border border-border bg-surface p-5">
        <div className="flex flex-col items-center gap-4 border-b border-border pb-5 sm:flex-row sm:items-start">
          {teacher.image ? (
            <img src={teacher.image} alt={fullName} className="size-20 shrink-0 rounded-full object-cover" />
          ) : (
            <span className="flex size-20 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              <UserIcon className="size-8" aria-hidden />
            </span>
          )}
          <div className="text-center sm:text-left">
            <p className="text-lg font-semibold text-ink">{fullName}</p>
            {teacher.position ? <p className="text-sm text-ink-secondary">{teacher.position}</p> : null}
            <div className="mt-2">
              <Badge tone={teacher.is_active ? 'success' : 'muted'}>{teacher.is_active ? 'Активен' : 'Неактивен'}</Badge>
            </div>
          </div>
        </div>

        <dl className="grid grid-cols-1 gap-4 py-5 sm:grid-cols-2">
          <Field icon={Mail} label="Email" value={teacher.user.email || '—'} />
          <Field icon={Phone} label="Телефон" value={teacher.phone || '—'} />
          <Field icon={Briefcase} label="Стаж" value={`${teacher.experience_years} ${pluralize(teacher.experience_years, 'год', 'года', 'лет')}`} />
          <Field icon={Calendar} label="Дата найма" value={teacher.hire_date ? formatDate(teacher.hire_date) : '—'} />
        </dl>

        {teacher.subjects.length > 0 ? (
          <div className="border-t border-border pt-5">
            <p className="mb-2 text-sm text-ink-secondary">Предметы</p>
            <div className="flex flex-wrap gap-1.5">
              {teacher.subjects.map((subject) => (
                <Badge key={subject.id} tone="brand">
                  {subject.name}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {teacher.bio ? (
          <div className="border-t border-border pt-5 mt-5">
            <p className="mb-2 text-sm text-ink-secondary">О себе</p>
            <p className="text-sm text-ink">{teacher.bio}</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function Field({ icon: Icon, label, value }: { icon: typeof Mail; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-ink-muted">
        <Icon className="size-4" aria-hidden />
      </span>
      <div>
        <dt className="text-xs text-ink-secondary">{label}</dt>
        <dd className="text-sm font-medium text-ink">{value}</dd>
      </div>
    </div>
  )
}
