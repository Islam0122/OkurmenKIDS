import { apiClient } from '@/api/client'
import type { ControlDetail, ControlLesson, ControlOverview, ControlPeriodKey, ControlStatus } from '@/types/control'

/** The Reports filter vocabulary plus `status`. A Trainer's own scoping
 * happens server-side regardless of what's passed here. */
export interface ControlParams {
  period: ControlPeriodKey
  start_date?: string
  end_date?: string
  teacher?: number
  group?: number
  subject?: number
  status?: ControlStatus
}

export interface ControlDetailParams extends Omit<ControlParams, 'group' | 'teacher' | 'status'> {
  group: number
  /** A Teacher id, or "none" for lessons without a responsible trainer. */
  teacher: number | 'none'
}

export const controlApi = {
  /** `GET /control/` — summary + one row per (responsible trainer, group), problems first. */
  overview: (params: ControlParams): Promise<ControlOverview> =>
    apiClient.get<ControlOverview>('/control/', { params }).then((r) => r.data),

  /** `GET /control/detail/` — one row and every lesson behind it, newest first. */
  detail: (params: ControlDetailParams): Promise<ControlDetail> =>
    apiClient.get<ControlDetail>('/control/detail/', { params }).then((r) => r.data),

  /** `GET /control/lessons/{id}/` — one lesson's full check. */
  lesson: (id: number): Promise<ControlLesson> =>
    apiClient.get<ControlLesson>(`/control/lessons/${id}/`).then((r) => r.data),
}
