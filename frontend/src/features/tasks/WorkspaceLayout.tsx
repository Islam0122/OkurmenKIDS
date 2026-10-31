import { ArrowLeft, ClipboardList, FileText, ScanLine } from 'lucide-react'

import { useAuth } from '@/hooks/useAuth'
import { workspaceFor } from '@/features/staffAttendance/roles'

import { WorkShell, type ShellNavItem } from '../operations/OperationsLayout'

/** Задачи и отчёты есть у каждого сотрудника, какой бы ни была его роль:
 * та же оболочка, что у кабинетов, и ссылка обратно в свой кабинет. */
export function WorkspaceLayout() {
  const { user } = useAuth()
  // Роли без своего кабинета (РОП, ДОП, продажи) возвращаются к отметке прихода.
  const home = workspaceFor(user?.role)?.to ?? '/attendance'
  const items: ShellNavItem[] = [
    { to: '/tasks', label: 'Мои задачи', icon: ClipboardList, end: true },
    { to: '/work-reports', label: 'Мои отчёты', icon: FileText },
  ]
  const footer: ShellNavItem[] = [
    { to: home, label: 'Вернуться в кабинет', icon: ArrowLeft },
    { to: '/attendance', label: 'Отметка прихода', icon: ScanLine },
  ]
  return <WorkShell title="Задачи и отчёты" items={items} footer={footer} label="Задачи и отчёты" />
}
