import { ClipboardList } from 'lucide-react'
import { Link } from 'react-router-dom'

import { NotificationsBell } from './NotificationsBell'

/** Шапка любого кабинета: «Мои задачи» и уведомления (задачи, отчёты,
 * дедлайны, проблемы) — у каждого сотрудника, какой бы ни была роль. */
export function WorkTools() {
  return (
    <div className="flex items-center">
      <Link to="/tasks" aria-label="Мои задачи" title="Мои задачи"
        className="flex size-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-surface-hover hover:text-ink">
        <ClipboardList className="size-5" aria-hidden />
      </Link>
      <NotificationsBell />
    </div>
  )
}
