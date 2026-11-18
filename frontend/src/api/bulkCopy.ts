import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type { BulkOperation, BulkOptions, BulkParams, BulkPreview } from '@/types/bulkCopy'

export { newOperationId } from '@/api/scoreCopy'

const BASE = '/bulk-copy/operations/'

/** Admin / staff with `bulk_copy.run_bulk_copy` — enforced by the backend. */
export const bulkCopyApi = {
  options: (group?: number): Promise<BulkOptions> =>
    apiClient.get<BulkOptions>(`${BASE}options/`, { params: group ? { group } : {} }).then((r) => r.data),
  /** Dry run — nothing is written. */
  preview: (params: BulkParams): Promise<BulkPreview> => apiClient.post<BulkPreview>(`${BASE}preview/`, params).then((r) => r.data),
  apply: (params: BulkParams & { fingerprint: string; operation_id: string; confirm_overwrite: boolean }): Promise<BulkOperation> =>
    apiClient.post<BulkOperation>(BASE, params).then((r) => r.data),
  history: (): Promise<Paginated<BulkOperation>> => apiClient.get<Paginated<BulkOperation>>(BASE).then((r) => r.data),
  undo: (id: number): Promise<BulkOperation> => apiClient.post<BulkOperation>(`${BASE}${id}/undo/`).then((r) => r.data),
}
