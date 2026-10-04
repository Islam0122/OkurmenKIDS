import { useParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { StatCard } from '@/components/ui/StatCard'
import { StatGrid } from '@/components/ui/StatGrid'
import { useStudent } from '@/hooks/useStudents'
import { ATTENDANCE_STATUS_LABELS } from '@/types/attendance'
import { formatDateShort } from '@/utils/format'

import { ResultsSummaryCards, ResultsTable } from '@/features/results/resultsUi'
import { useResultsSummary } from '@/hooks/useResults'

import { useStudentHistory } from './useStudentHistory'

export function StudentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const studentId = Number(id)

  const { data: student, isPending, isError, refetch } = useStudent(studentId)
  const history = useStudentHistory(student?.id, student?.group)

  if (isPending) return <LoadingState label="Загружаем студента…" />
  if (isError || !student) return <ErrorState onRetry={() => void refetch()} />

  return (
    <div>
      <PageHeader
        title={student.full_name}
        description={student.group_name ?? 'Без группы'}
        actions={<Badge tone={student.is_active ? 'success' : 'muted'}>{student.is_active ? 'Активен' : 'Неактивен'}</Badge>}
      />

      <dl className="mb-6 grid grid-cols-1 gap-4 card card-body sm:grid-cols-3">
        <div>
          <dt className="text-sm text-ink-secondary">Телефон</dt>
          <dd className="mt-0.5 font-medium text-ink">{student.phone || '—'}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-secondary">Телефон родителя</dt>
          <dd className="mt-0.5 font-medium text-ink">{student.parent_phone || '—'}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-secondary">Группа</dt>
          <dd className="mt-0.5 font-medium text-ink">{student.group_name ?? '—'}</dd>
        </div>
      </dl>

      {history.isPending ? <LoadingState label="Считаем статистику…" /> : null}
      {history.isError ? <ErrorState onRetry={() => void history.refetch()} /> : null}

      {history.data ? (
        <>
          <StatGrid columns={3} className="mb-6">
            <StatCard
              label="Посещаемость"
              value={history.data.attendancePercent !== null ? `${history.data.attendancePercent}%` : '—'}
              hint={`${history.data.attendanceTotal} занятий отмечено`}
            />
            <StatCard
              label="Домашние задания"
              value={history.data.homeworkCompletionPercent !== null ? `${history.data.homeworkCompletionPercent}%` : '—'}
              hint={`${history.data.homeworkCompleted} из ${history.data.homeworkAssigned} сдано`}
            />
            <StatCard label="Средний балл" value={history.data.averageScore !== null ? `${history.data.averageScore}/10` : '—'} />
          </StatGrid>

          <div className="card">
            <p className="border-b border-border px-5 py-3 text-sm font-medium text-ink-secondary">История занятий</p>
            {history.data.rows.length === 0 ? (
              <div className="p-5">
                <EmptyState title="История пока пуста" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Дата</th>
                      <th>Предмет / тема</th>
                      <th>Посещаемость</th>
                      <th>ДЗ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.data.rows.map((row) => (
                      <tr key={row.lesson.id}>
                        <td>{formatDateShort(row.lesson.date)}</td>
                        <td>
                          {row.lesson.subject_name ?? '—'}
                          {row.lesson.topic ? <span className="text-ink-secondary"> — {row.lesson.topic}</span> : null}
                        </td>
                        <td>
                          {row.attendance?.status ? (
                            <Badge
                              tone={
                                row.attendance.status === 'present'
                                  ? 'success'
                                  : row.attendance.status === 'absent'
                                    ? 'danger'
                                    : 'warning'
                              }
                            >
                              {ATTENDANCE_STATUS_LABELS[row.attendance.status]}
                            </Badge>
                          ) : (
                            <span className="text-ink-muted">—</span>
                          )}
                        </td>
                        <td>
                          {row.result ? (row.result.score !== null ? `${row.result.score}/10` : row.result.status_display) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}

      <StudentTestResults studentId={student.id} />
    </div>
  )
}

/** «Результаты тестов» — the student's finished tests (backend-scoped: a
 * trainer sees them only for students of their own groups). */
function StudentTestResults({ studentId }: { studentId: number }) {
  const filters = { student: String(studentId) }
  const summary = useResultsSummary(filters)
  return (
    <div className="mt-8 space-y-4">
      {summary.data && summary.data.attempts ? <ResultsSummaryCards summary={summary.data} variant="compact" /> : null}
      <ResultsTable filters={filters} columns={['test', 'subject', 'group', 'teacher', 'attempt']} title="Результаты тестов" />
    </div>
  )
}
