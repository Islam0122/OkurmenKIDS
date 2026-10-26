/** `team_lead` — руководитель тренеров: читает всю академию, ничего не изменяет.
 * `assistant` — ежедневные операции академии, только через Assistant Workspace (/assistant). */
/** `accountant` — бухгалтерия (/accounting): расчёт зарплат, выплаты, отчёты.
 * `director` — утверждение начислений и финансовая сводка (/accounting). */
/** Сотрудники с базовым доступом — пока только вход и отметка прихода и ухода
 * (/attendance/staff); личные кабинеты в разработке. */
export type StaffOnlyRole = 'dop' | 'rop' | 'rom' | 'operations_director' | 'hr_manager' | 'sales_manager' | 'marketing'
export type UserRole = 'admin' | 'teacher' | 'team_lead' | 'assistant' | 'accountant' | 'director' | StaffOnlyRole

/** `apps.users.serializers.UserSerializer` — read-only in full. */
export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  role: UserRole
  is_verified: boolean
  is_active: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

/** `POST /api/v1/auth/login/` */
export interface LoginResponse {
  access: string
  refresh: string
  user: User
}

/** `POST /api/v1/auth/refresh/` — SimpleJWT with ROTATE_REFRESH_TOKENS,
 * so a fresh refresh token comes back on every call and must be persisted. */
export interface RefreshResponse {
  access: string
  refresh: string
}
