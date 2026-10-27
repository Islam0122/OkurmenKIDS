import axios from 'axios'

import { API_BASE_URL } from '@/api/client'
import type { ApplyInput, ApplyResult, CareersFilters, CareersListParams, PublicVacancy, PublicVacancyList } from '@/types/careers'

/** Отдельный клиент без токена и без обновления сессии: карьерный сайт никогда
 * не отправляет на сервер токен посетителя или вошедшего сотрудника. */
const publicClient = axios.create({ baseURL: API_BASE_URL })

export const careersApi = {
  filters: () => publicClient.get<CareersFilters>('/public/careers/filters/').then((r) => r.data),
  vacancies: (params: CareersListParams) =>
    publicClient.get<PublicVacancyList>('/public/careers/vacancies/', { params }).then((r) => r.data),
  vacancy: (slug: string) => publicClient.get<PublicVacancy>(`/public/careers/vacancies/${encodeURIComponent(slug)}/`).then((r) => r.data),
  apply: (slug: string, input: ApplyInput) => {
    const form = new FormData()
    for (const [key, value] of Object.entries(input)) {
      if (key === 'resume') continue
      form.append(key, typeof value === 'boolean' ? String(value) : String(value ?? ''))
    }
    if (input.resume) form.append('resume', input.resume)
    return publicClient
      .post<ApplyResult>(`/public/careers/vacancies/${encodeURIComponent(slug)}/apply/`, form)
      .then((r) => r.data)
  },
}
