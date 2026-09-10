import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

export interface DataTableColumn<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  className?: string
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  rows: T[]
  getRowKey: (row: T) => string | number
  onRowClick?: (row: T) => void
}

export function DataTable<T>({ columns, rows, getRowKey, onRowClick }: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface">
      <table className="w-full min-w-full divide-y divide-border text-sm">
        <thead className="bg-surface-muted">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={cn('px-4 py-3 text-left font-medium text-ink-secondary', column.className)}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => (
            <tr
              key={getRowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === 'Enter') onRowClick(row)
                    }
                  : undefined
              }
              tabIndex={onRowClick ? 0 : undefined}
              className={cn(onRowClick && 'cursor-pointer hover:bg-surface-hover focus-visible:bg-surface-hover')}
            >
              {columns.map((column) => (
                <td key={column.key} className={cn('px-4 py-3 text-ink', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
