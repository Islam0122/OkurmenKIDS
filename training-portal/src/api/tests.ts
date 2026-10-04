import type { TrainingTest } from '@/types'

import { apiClient } from './client'

export const getTests = () => apiClient.get<TrainingTest[]>('/tests/')
export const getTest = (testId: string) => apiClient.get<TrainingTest>(`/tests/${encodeURIComponent(testId)}/`)
