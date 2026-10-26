import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type { HREmployee, HREmployeeCreateInput, HREmployeeInput, HREmployeesParams, HRMeta } from '@/types/hr'

const BASE = '/hr/employees'

/** Раздел «Сотрудники» HR-менеджера (backend: apps.users.hr). Все
 * ограничения проверяет сервер. */
export const hrApi = {
  meta: () => apiClient.get<HRMeta>(`${BASE}/meta/`).then((r) => r.data),
  list: (params: HREmployeesParams) => apiClient.get<Paginated<HREmployee>>(`${BASE}/`, { params }).then((r) => r.data),
  create: (payload: HREmployeeCreateInput) => apiClient.post<HREmployee>(`${BASE}/`, payload).then((r) => r.data),
  update: (id: number, payload: Partial<HREmployeeInput>) =>
    apiClient.patch<HREmployee>(`${BASE}/${id}/`, payload).then((r) => r.data),
  setPassword: (id: number, password: string, passwordConfirm: string) =>
    apiClient
      .post<HREmployee>(`${BASE}/${id}/set-password/`, { password, password_confirm: passwordConfirm })
      .then((r) => r.data),
  setActive: (id: number, active: boolean) =>
    apiClient.post<HREmployee>(`${BASE}/${id}/${active ? 'activate' : 'deactivate'}/`).then((r) => r.data),
}
