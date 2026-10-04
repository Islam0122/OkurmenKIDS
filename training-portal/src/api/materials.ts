import type { UsefulLink } from '@/types'

import { apiClient } from './client'

export const getMaterials = () => apiClient.get<UsefulLink[]>('/links/')
