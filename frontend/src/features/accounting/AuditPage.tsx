import { useState } from 'react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useAuditLog } from '@/hooks/useAccounting'

import { formatDateTime } from './shared'

const ENTITIES = [
  { value: 'payroll', label: 'Начисления' },
  { value: 'payrollpayment', label: 'Выплаты' },
  { value: 'payrolladjustment', label: 'Корректировки' },
  { value: 'salaryrule', label: 'Зарплатные правила' },
  { value: 'employeesalaryprofile', label: 'Зарплатные профили' },
  { value: 'studentpayment', label: 'Платежи студентов' },
  { value: 'payrollperiod', label: 'Периоды' },
]
const ENTITY_LABEL = Object.fromEntries(ENTITIES.map((e) => [e.value, e.label]))

function changes(oldValues: Record<string, unknown>, newValues: Record<string, unknown>): string {
  return Object.keys(newValues)
    .filter((k) => k !== 'lines' && JSON.stringify(oldValues[k]) !== JSON.stringify(newValues[k]))
    .map((k) => `${k}: ${oldValues[k] === undefined ? '' : `${String(oldValues[k] ?? '—')} → `}${String(newValues[k] ?? '—')}`)
    .join('; ')
}

/** Журнал финансовых изменений — только чтение для всех ролей. */
export function AuditPage() {
  const [entity, setEntity] = useState('')
  const [page, setPage] = useState(1)
  const log = useAuditLog({ entity_type: entity || undefined, page })

  return (
    <div>
      <PageHeader title="Журнал изменений" description="Каждое финансовое действие: кто, когда, что изменил и почему. Записи нельзя изменить или удалить." />
      <FilterBar>
        <FilterField>
          <Select aria-label="Объект" value={entity} placeholder="Все объекты" options={ENTITIES}
            onChange={(e) => { setEntity(e.target.value); setPage(1) }} />
        </FilterField>
      </FilterBar>
      {log.isLoading ? <LoadingState /> : log.isError ? <ErrorState onRetry={() => log.refetch()} /> :
        log.data?.results.length === 0 ? <EmptyState title="Записей нет" /> : (
          <div className="card overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Изменения</th><th>Причина</th></tr></thead>
              <tbody>
                {log.data?.results.map((e) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap text-sm">{formatDateTime(e.created_at)}</td>
                    <td>{e.actor_name}</td>
                    <td>{e.action}</td>
                    <td className="whitespace-nowrap">
                      {e.payroll ? <Link className="text-brand-700 hover:underline" to={`/accounting/payrolls/${e.payroll}`}>{ENTITY_LABEL[e.entity_type] ?? e.entity_type} #{e.entity_id}</Link>
                        : `${ENTITY_LABEL[e.entity_type] ?? e.entity_type} #${e.entity_id}`}
                    </td>
                    <td className="max-w-md text-xs text-ink-secondary">{changes(e.old_values, e.new_values) || '—'}</td>
                    <td className="text-sm">{e.reason || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {log.data && (log.data.next || log.data.previous) ? (
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" disabled={!log.data.previous} onClick={() => setPage(page - 1)}>Назад</Button>
          <Button variant="ghost" size="sm" disabled={!log.data.next} onClick={() => setPage(page + 1)}>Далее</Button>
        </div>
      ) : null}
    </div>
  )
}
