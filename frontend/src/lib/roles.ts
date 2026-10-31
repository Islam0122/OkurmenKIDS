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
  operations_director: 'Операционный директор',
  hr_manager: 'HR-менеджер',
  sales_manager: 'Менеджер по продажам',
  marketing: 'Маркетинг',
}

/** Mirrors `User.STAFF_ONLY_ROLES`: these roles only sign in and mark
 * arrival/departure (backend: apps.accounting.access isolates the rest). */
export const STAFF_ONLY_ROLES: StaffOnlyRole[] = [
  'dop', 'rop', 'operations_director', 'hr_manager', 'sales_manager', 'marketing',
]

export function isStaffOnlyRole(role: UserRole | undefined): role is StaffOnlyRole {
  return (STAFF_ONLY_ROLES as (UserRole | undefined)[]).includes(role)
}

/** Роли без своего кабинета: после входа — отметка прихода и ухода, свои
 * задачи и отчёты (/tasks). У HR-менеджера есть HR-кабинет (/hr), у
 * маркетинга — кабинет маркетинга (/marketing), у операционного директора —
 * /operations. */
export function hasCabinetInDevelopment(role: UserRole | undefined): boolean {
  return isStaffOnlyRole(role) && role !== 'hr_manager' && role !== 'marketing' && role !== 'operations_director'
}

/** Кабинет операционного директора (/operations) — ему, директору и
 * администратору. Mirrors `apps.operations.permissions.can_oversee`. */
export function canOverseeOperations(role: UserRole | undefined): boolean {
  return role === 'operations_director' || role === 'director' || role === 'admin'
}

/** Свои задачи, отчёты и уведомления (/tasks, /work-reports) есть у каждого сотрудника. */
export const PERSONAL_WORK_PATHS = ['/tasks', '/work-reports']

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
  const personal = PERSONAL_WORK_PATHS.some((path) => target.startsWith(path))
  if (role === 'accountant' && !target.startsWith('/accounting') && !target.startsWith('/finance') && !personal) return '/accounting'
  if (role === 'hr_manager') return target.startsWith('/hr') || target.startsWith('/attendance') || personal ? target : '/hr'
  if (role === 'marketing') return target.startsWith('/marketing') || target.startsWith('/attendance') || personal ? target : '/marketing'
  if (role === 'operations_director') return target.startsWith('/operations') || target.startsWith('/attendance') || personal ? target : '/operations'
  if (isStaffOnlyRole(role) && !target.startsWith('/attendance') && !personal) return '/attendance/staff'
  return target
}
