import type { Video } from '@/types'

import { apiClient } from './client'

export const getVideos = () => apiClient.get<Video[]>('/videos/')
