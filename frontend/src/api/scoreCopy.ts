import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type { ScoreCopyOperation, ScoreCopyOptions, ScoreCopyParams, ScoreCopyPreview } from '@/types/scoreCopy'

const BASE = '/scholarship-score-copies/'

/** Admin / staff with `scholarships.copy_scores` only — the backend enforces it. */
export const scoreCopyApi = {
  options: (group?: number): Promise<ScoreCopyOptions> =>
    apiClient.get<ScoreCopyOptions>(`${BASE}options/`, { params: group ? { group } : {} }).then((r) => r.data),

  /** Dry run: nothing is written. */
  preview: (params: ScoreCopyParams): Promise<ScoreCopyPreview> =>
    apiClient.post<ScoreCopyPreview>(`${BASE}preview/`, params).then((r) => r.data),

  /** One transaction; `operation_id` makes a retried request safe (applied once). */
  apply: (
    params: ScoreCopyParams & { fingerprint: string; operation_id: string; confirm_overwrite: boolean },
  ): Promise<ScoreCopyOperation> => apiClient.post<ScoreCopyOperation>(BASE, params).then((r) => r.data),

  history: (page = 1): Promise<Paginated<ScoreCopyOperation>> =>
    apiClient.get<Paginated<ScoreCopyOperation>>(BASE, { params: { page } }).then((r) => r.data),

  undo: (id: number): Promise<ScoreCopyOperation> =>
    apiClient.post<ScoreCopyOperation>(`${BASE}${id}/undo/`).then((r) => r.data),
}

/** RFC 4122 v4 — the backend's UUIDField rejects anything else. */
export function newOperationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
