import type { StaffOnlyRole, UserRole } from '@/types/auth'

/** UI-only role helpers. Every permission is enforced by the backend
 * (apps.users.permissions) — these only decide what the UI offers. */

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: 'Администратор',
  teacher: 'Тренер',
  team_lead: 'Team Lead',
  assistant: 'Ассистент',
  accountant: 'Бухгалтер',
  director: 'Директор',
  dop: 'ДОП',
  rop: 'РОП',
  rom: 'РОМ',
  operations_director: 'Операционный директор',
  hr_manager: 'HR-менеджер',
  sales_manager: 'Менеджер по продажам',
  marketing: 'Маркетинг',
}

/** Mirrors `User.STAFF_ONLY_ROLES`: these roles only sign in and mark
 * arrival/departure (backend: apps.accounting.access isolates the rest). */
export const STAFF_ONLY_ROLES: StaffOnlyRole[] = [
  'dop', 'rop', 'rom', 'operations_director', 'hr_manager', 'sales_manager', 'marketing',
]

export function isStaffOnlyRole(role: UserRole | undefined): role is StaffOnlyRole {
  return (STAFF_ONLY_ROLES as (UserRole | undefined)[]).includes(role)
}

/** Роли без своего кабинета: после входа — только отметка прихода и ухода.
 * У HR-менеджера есть HR-кабинет (/hr), у маркетинга — кабинет маркетинга
 * (/marketing). */
export function hasCabinetInDevelopment(role: UserRole | undefined): boolean {
  return isStaffOnlyRole(role) && role !== 'hr_manager' && role !== 'marketing'
}

/** The Assistant works only in the Assistant Workspace (/assistant), never in /app. */
export function isAssistant(role: UserRole | undefined): boolean {
  return role === 'assistant'
}

export function isTeamLead(role: UserRole | undefined): boolean {
  return role === 'team_lead'
}

/** Admin or Team Lead: reads the whole academy (every trainer/group/student).
 * Mirrors `apps.users.permissions.can_view_academy` — never a write gate. */
export function seesWholeAcademy(role: UserRole | undefined): boolean {
  return role === 'admin' || role === 'team_lead'
}

/** Бухгалтер и Директор работают только в разделе бухгалтерии (/accounting). */
export function isAccountingRole(role: UserRole | undefined): boolean {
  return role === 'accountant' || role === 'director'
}

/** Where a role lands after sign-in. The Accountant lives only in /accounting
 * (backend: apps.accounting.access — every LMS URL answers it 403). */
export function homeFor(role: UserRole | undefined, target: string): string {
  if (role === 'accountant' && !target.startsWith('/accounting') && !target.startsWith('/finance')) return '/accounting'
  if (role === 'hr_manager') return target.startsWith('/hr') || target.startsWith('/attendance') ? target : '/hr'
  if (role === 'marketing') return target.startsWith('/marketing') || target.startsWith('/attendance') ? target : '/marketing'
  if (isStaffOnlyRole(role) && !target.startsWith('/attendance')) return '/attendance/staff'
  return target
}
