import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'

import { careersApi } from '@/api/careers'
import type { ApplyInput, CareersListParams } from '@/types/careers'

/** Публичный карьерный сайт: только опубликованные вакансии и отправка отклика. */
export function useCareersFilters() {
  return useQuery({ queryKey: ['careers', 'filters'], queryFn: careersApi.filters, staleTime: 5 * 60_000 })
}

export function useCareersVacancies(params: CareersListParams) {
  return useQuery({ queryKey: ['careers', 'list', params], queryFn: () => careersApi.vacancies(params), placeholderData: keepPreviousData })
}

export function useCareersVacancy(slug: string) {
  return useQuery({ queryKey: ['careers', 'vacancy', slug], queryFn: () => careersApi.vacancy(slug), retry: false })
}

export function useApply(slug: string) {
  return useMutation({ mutationFn: (input: ApplyInput) => careersApi.apply(slug, input) })
}
