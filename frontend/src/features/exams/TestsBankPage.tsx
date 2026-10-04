import { BookOpen } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { examsApi } from '@/api/exams'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { DataTable } from '@/components/ui/DataTable'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'

/** «Тесты» — the test bank, view only (Admin edits tests in the admin
 * section; a Team Lead only reads them and runs sessions from «Сессии»). */
export function TestsBankPage() {
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['exams', 'tests', 'bank', page],
    queryFn: () => examsApi.tests(page),
  })

  return (
    <div>
      <PageHeader title="Тесты" description="Опубликованные тесты академии — только просмотр. Сессию по тесту создают в разделе «Сессии»." />
      {isPending ? <LoadingState label="Загружаем тесты…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.results.length === 0 ? <EmptyState icon={BookOpen} title="Опубликованных тестов нет" /> : null}
      {data && data.results.length > 0 ? (
        <div className="space-y-3">
          <DataTable
            rows={data.results}
            getRowKey={(row) => row.id}
            columns={[
              { key: 'title', header: 'Тест', render: (row) => <span className="font-medium text-ink">{row.title}</span> },
              { key: 'subject', header: 'Предмет', render: (row) => row.subject_name ?? '—' },
              { key: 'level', header: 'Уровень', render: (row) => row.level_display },
              { key: 'questions', header: 'Вопросов', render: (row) => row.question_count ?? '—' },
              { key: 'time', header: 'Время', render: (row) => (row.time_limit_minutes ? `${row.time_limit_minutes} мин` : '—') },
              { key: 'pass', header: 'Проходной балл', render: (row) => `${row.passing_score}%` },
              { key: 'status', header: 'Статус', render: (row) => <Badge tone="success">{row.status_display}</Badge> },
            ]}
          />
          <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
        </div>
      ) : null}
    </div>
  )
}
