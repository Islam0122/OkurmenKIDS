import { STAFF_ONLY_ROLES, isStaffOnlyRole } from '@/lib/roles'
import type { UserRole } from '@/types/auth'

/** Личная страница отметки для каждой категории сотрудников. */
export type PersonalVariant = 'teacher' | 'accounting' | 'assistant' | 'office' | 'staff'

export const VARIANT_ROLES: Record<PersonalVariant, UserRole[]> = {
  teacher: ['teacher'],
  accounting: ['accountant'],
  assistant: ['assistant'],
  // Администрация и офис: администраторы, директор, руководитель тренеров.
  office: ['admin', 'director', 'team_lead'],
  // ДОП, РОП, РОМ, операционный директор, HR, продажи, маркетинг: личные
  // кабинеты в разработке — пока только отметка.
  staff: STAFF_ONLY_ROLES,
}

export const VARIANT_TITLE: Record<PersonalVariant, string> = {
  teacher: 'Приход и уход — тренер',
  accounting: 'Приход и уход — бухгалтерия',
  assistant: 'Приход и уход — ассистент',
  office: 'Приход и уход — офис',
  staff: 'Приход и уход — сотрудник',
}

export function personalPathFor(role: UserRole | undefined): string {
  switch (role) {
    case 'teacher':
      return '/attendance/teacher'
    case 'accountant':
      return '/attendance/accounting'
    case 'assistant':
      return '/attendance/assistant'
    case undefined:
      return '/attendance/office'
    default:
      if (isStaffOnlyRole(role)) return '/attendance/staff'
      return '/attendance/office'
  }
}

/** Основной раздел роли — куда ведёт «назад в LMS»; null — другого раздела у роли нет. */
export function workspaceFor(role: UserRole | undefined): { to: string; label: string } | null {
  if (role === 'hr_manager') return { to: '/hr', label: 'HR-кабинет' }
  if (isStaffOnlyRole(role)) return null
  if (role === 'assistant') return { to: '/assistant', label: 'Assistant Workspace' }
  if (role === 'accountant' || role === 'director') return { to: '/accounting', label: 'Бухгалтерия' }
  return { to: '/app/dashboard', label: 'LMS' }
}
