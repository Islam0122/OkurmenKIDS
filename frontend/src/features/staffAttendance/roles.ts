import type { UserRole } from '@/types/auth'

/** Личная страница отметки для каждой категории сотрудников. */
export type PersonalVariant = 'teacher' | 'accounting' | 'assistant' | 'office'

export const VARIANT_ROLES: Record<PersonalVariant, UserRole[]> = {
  teacher: ['teacher'],
  accounting: ['accountant'],
  assistant: ['assistant'],
  // Администрация и офис: администраторы, директор, руководитель тренеров.
  office: ['admin', 'director', 'team_lead'],
}

export const VARIANT_TITLE: Record<PersonalVariant, string> = {
  teacher: 'Приход и уход — тренер',
  accounting: 'Приход и уход — бухгалтерия',
  assistant: 'Приход и уход — ассистент',
  office: 'Приход и уход — офис',
}

export function personalPathFor(role: UserRole | undefined): string {
  switch (role) {
    case 'teacher':
      return '/attendance/teacher'
    case 'accountant':
      return '/attendance/accounting'
    case 'assistant':
      return '/attendance/assistant'
    default:
      return '/attendance/office'
  }
}

/** Основной раздел роли — куда ведёт «назад в LMS». */
export function workspaceFor(role: UserRole | undefined): { to: string; label: string } {
  if (role === 'assistant') return { to: '/assistant', label: 'Assistant Workspace' }
  if (role === 'accountant' || role === 'director') return { to: '/accounting', label: 'Бухгалтерия' }
  return { to: '/app/dashboard', label: 'LMS' }
}
