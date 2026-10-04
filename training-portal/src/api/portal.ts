import type { PortalSettings } from '@/types'

import { apiClient } from './client'

export const getPortal = () => apiClient.get<PortalSettings>('/portal/')
