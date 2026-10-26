import type { StaffOnlyRole } from '@/types/auth'

/** `apps.users.hr.HREmployeeSerializer` — пароль никогда не возвращается. */
export interface HREmployee {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  role: StaffOnlyRole
  role_label: string
  is_active: boolean
  created_at: string
  last_login: string | null
}

export interface HRRoleOption {
  value: StaffOnlyRole
  label: string
}

/** `GET /api/v1/hr/employees/meta/` */
export interface HRMeta {
  roles: HRRoleOption[]
  protected_roles: HRRoleOption[]
}

export interface HREmployeeInput {
  username: string
  email: string
  first_name: string
  last_name: string
  role: StaffOnlyRole
}

export interface HREmployeeCreateInput extends HREmployeeInput {
  password: string
  password_confirm: string
}

export interface HREmployeesParams {
  search?: string
  role?: string
  is_active?: 'true' | 'false'
  page?: number
}
