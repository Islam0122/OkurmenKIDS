import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { CareersFilters, PublicVacancy } from '@/types/careers'

vi.mock('@/api/careers', () => ({
  careersApi: { filters: vi.fn(), vacancies: vi.fn(), vacancy: vi.fn(), apply: vi.fn() },
}))

import { careersApi } from '@/api/careers'

import { CareersHomePage } from './CareersHomePage'
import { validateApply } from './ApplyForm'
import { VacancyPage } from './VacancyPage'

const api = vi.mocked(careersApi)

const filters: CareersFilters = {
  total: 1, departments: ['Продажи'], locations: ['Бишкек'], work_formats: [{ value: 'office', label: 'В офисе' }],
  employment_types: [{ value: 'full_time', label: 'Полная занятость' }], sources: [{ value: 'social', label: 'Социальные сети' }],
  resume_max_mb: 5,
}

const vacancy: PublicVacancy = {
  slug: 'menedzher-po-prodazham', title: 'Менеджер по продажам', department: 'Продажи', location: 'Бишкек', work_format: 'office',
  work_format_label: 'В офисе', employment_type: 'full_time', employment_type_label: 'Полная занятость',
  salary: { min: 40000, max: 60000, currency: 'KGS', currency_label: 'сом' }, summary: 'Продажи курсов для детей',
  published_at: '2026-10-01', closes_on: null, is_open: true, description: 'Работа с родителями.',
  responsibilities: ['Звонки'], requirements: ['Опыт продаж'], nice_to_have: [], conditions: ['Обучение'],
  selection_stages: ['Собеседование с HR', 'Встреча с РОП'],
}

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR', undefined, undefined, { status, data } as AxiosResponse)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.filters.mockResolvedValue(filters)
  api.vacancies.mockResolvedValue({ count: 1, page: 1, page_size: 12, results: [vacancy] })
  api.vacancy.mockResolvedValue(vacancy)
})

describe('главная карьерного сайта', () => {
  it('первый экран, разделы и вакансии из API с реальным числом вакансий', async () => {
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Создавайте будущее вместе с OKURMEN KIDS')
    expect(await screen.findByRole('heading', { name: 'Менеджер по продажам' })).toBeInTheDocument()
    const vacancies = within(document.getElementById('vacancies') as HTMLElement)
    expect(vacancies.getByText('40 000 – 60 000 сом')).toBeInTheDocument()
    expect(vacancies.getByText('1 вакансия с открытым приёмом откликов')).toBeInTheDocument()
    expect(vacancies.getByRole('link', { name: 'Подробнее' })).toHaveAttribute('href', '/careers/vacancies/menedzher-po-prodazham')
    expect(screen.getByRole('link', { name: 'Откликнуться на вакансию «Менеджер по продажам»' }))
      .toHaveAttribute('href', '/careers/vacancies/menedzher-po-prodazham#apply')
    for (const name of ['Мы учим детей и подростков технологиям, языку и умению работать вместе — так, чтобы знания оставались с ними надолго.',
      'Почему стоит присоединиться к команде', 'Одна команда — много профессий', 'Открытые вакансии', 'От отклика до первого рабочего дня',
      'Давайте создавать будущее вместе', 'Частые вопросы кандидатов']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    }
    expect(document.title).toContain('Карьера в OKURMEN KIDS')
  })

  it('без фотографии первый экран — живая витрина реальных вакансий, без битых изображений', async () => {
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    expect(screen.getByText('Сейчас ищем')).toBeInTheDocument()
    const showcase = await screen.findAllByRole('link', { name: /Менеджер по продажам/ })
    expect(showcase[0]).toHaveAttribute('href', '/careers/vacancies/menedzher-po-prodazham')
    expect(document.querySelectorAll('section img')).toHaveLength(0)
    expect(screen.getByText('Тренеры, ассистенты и специалисты работают над одним делом')).toBeInTheDocument()
    expect(api.vacancies).toHaveBeenCalledWith(expect.objectContaining({ page_size: 50, ordering: 'newest' }))
  })

  it('плитки направлений с реальным числом вакансий фильтруют список', async () => {
    const user = userEvent.setup()
    api.vacancies.mockResolvedValue({ count: 2, page: 1, page_size: 50, results: [vacancy, { ...vacancy, slug: 'smm', title: 'SMM-специалист', department: 'Маркетинг' }] })
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    const tile = await screen.findByRole('button', { name: /Маркетинг/ })
    expect(tile).toHaveTextContent('1 вакансия')
    await user.click(tile)
    await waitFor(() => expect(api.vacancies).toHaveBeenLastCalledWith(expect.objectContaining({ department: 'Маркетинг', page_size: 10 })))
    expect(tile).toHaveAttribute('aria-pressed', 'true')
  })

  it('кнопки первого экрана ведут к вакансиям и к команде', async () => {
    const user = userEvent.setup()
    const scrolled: string[] = []
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) { scrolled.push(this.id) })
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    await user.click(screen.getByRole('link', { name: /Смотреть вакансии/ }))
    await user.click(screen.getByRole('link', { name: 'Познакомиться с командой' }))
    await user.click(screen.getByRole('link', { name: /Выбрать вакансию/ }))
    expect(scrolled).toEqual(['vacancies', 'team', 'vacancies'])
  })

  it('поиск, фильтры и сортировка уходят на сервер', async () => {
    const user = userEvent.setup()
    api.filters.mockResolvedValue({ ...filters, total: 5 })
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    await screen.findByRole('heading', { name: 'Менеджер по продажам' })
    await user.type(await screen.findByLabelText('Поиск вакансий'), 'продаж')
    await user.click(screen.getByRole('button', { name: 'Найти' }))
    await waitFor(() => expect(api.vacancies).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'продаж', page: 1 })))
    await user.selectOptions(screen.getByLabelText('Формат работы'), 'office')
    await user.selectOptions(screen.getByLabelText('Сортировка'), 'salary_desc')
    await waitFor(() => expect(api.vacancies).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'продаж', work_format: 'office', ordering: 'salary_desc' })))
  })

  it('при паре вакансий фильтры не нужны', async () => {
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    await screen.findByRole('heading', { name: 'Менеджер по продажам' })
    expect(screen.queryByLabelText('Поиск вакансий')).not.toBeInTheDocument()
  })

  it('пустой список и ошибка', async () => {
    api.vacancies.mockResolvedValueOnce({ count: 0, page: 1, page_size: 10, results: [] })
    const { unmount } = renderWithProviders(<CareersHomePage />, { route: '/careers' })
    expect(await screen.findByText('Открытых вакансий пока нет')).toBeInTheDocument()
    unmount()
    api.vacancies.mockRejectedValue(axiosError(500, { detail: 'Сервер недоступен' }))
    renderWithProviders(<CareersHomePage />, { route: '/careers' })
    expect(await screen.findByText('Не удалось загрузить вакансии')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument()
  })
})

describe('страница вакансии', () => {
  function renderPage(slug = 'menedzher-po-prodazham') {
    return renderWithProviders(<Routes><Route path="/careers/vacancies/:slug" element={<VacancyPage />} /></Routes>, { route: `/careers/vacancies/${slug}` })
  }

  it('показывает разделы, SEO-метаданные и JobPosting', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { level: 1, name: 'Менеджер по продажам' })).toBeInTheDocument()
    expect(screen.getByText('Опыт продаж')).toBeInTheDocument()
    expect(screen.getByText('Встреча с РОП')).toBeInTheDocument()
    expect(document.title).toBe('Менеджер по продажам — вакансия OKURMEN KIDS')
    expect(document.head.querySelector('meta[name="description"]')?.getAttribute('content')).toBe('Продажи курсов для детей')
    const ld = JSON.parse(document.head.querySelector('script[type="application/ld+json"]')?.textContent ?? '{}')
    expect(ld).toMatchObject({ '@type': 'JobPosting', title: 'Менеджер по продажам', employmentType: 'FULL_TIME', datePosted: '2026-10-01' })
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute('href')).toContain('/careers/vacancies/menedzher-po-prodazham')
  })

  it('закрытая и несуществующая вакансия', async () => {
    api.vacancy.mockRejectedValueOnce(axiosError(410, { code: 'vacancy_closed', title: 'Маркетолог' }))
    const { unmount } = renderPage('marketolog')
    expect(await screen.findByText('«Маркетолог» — приём откликов закрыт')).toBeInTheDocument()
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex')
    unmount()
    api.vacancy.mockRejectedValueOnce(axiosError(404, { code: 'not_found' }))
    renderPage('net')
    expect(await screen.findByRole('heading', { name: 'Вакансия не найдена' })).toBeInTheDocument()
  })

  it('отклик: проверка полей, отправка одним ключом и номер заявки', async () => {
    const user = userEvent.setup()
    api.apply.mockResolvedValue({ number: '2026-K7QM3D', vacancy: { title: 'Менеджер по продажам', slug: vacancy.slug }, message: 'Заявка отправлена.' })
    renderPage()
    const form = await screen.findByRole('form', { name: 'Отклик на вакансию «Менеджер по продажам»' })
    await user.click(within(form).getByRole('button', { name: 'Отправить заявку' }))
    expect(within(form).getByText('Укажите фамилию и имя.')).toBeInTheDocument()
    expect(within(form).getByText('Укажите телефон.')).toBeInTheDocument()
    expect(within(form).getByText('Нужно согласие на обработку персональных данных.')).toBeInTheDocument()
    expect(api.apply).not.toHaveBeenCalled()
    await user.type(within(form).getByLabelText(/ФИО/), 'Асанов Бакыт')
    await user.type(within(form).getByLabelText(/Телефон/), '+996 555 123 456')
    await user.type(within(form).getByLabelText(/Электронная почта/), 'bakyt@mail.kg')
    const file = new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' })
    await user.upload(within(form).getByLabelText(/Резюме/), file)
    await user.click(within(form).getByLabelText(/Я согласен/))
    await user.click(within(form).getByRole('button', { name: 'Отправить заявку' }))
    expect(await screen.findByText('2026-K7QM3D')).toBeInTheDocument()
    expect(api.apply).toHaveBeenCalledTimes(1)
    const [slug, input] = api.apply.mock.calls[0]
    expect(slug).toBe('menedzher-po-prodazham')
    expect(input).toMatchObject({ full_name: 'Асанов Бакыт', phone: '+996 555 123 456', email: 'bakyt@mail.kg', consent: true, website: '', resume: file })
    expect(input.submission_token).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('ошибки сервера показываются у полей; повторная попытка — с тем же ключом', async () => {
    const user = userEvent.setup()
    api.apply
      .mockRejectedValueOnce(axiosError(400, { email: ['Введите правильный адрес электронной почты.'] }))
      .mockRejectedValueOnce(axiosError(409, { detail: 'Вы уже откликнулись на эту вакансию — заявка у нас, HR свяжется с вами.', code: 'already_applied' }))
    renderPage()
    const form = await screen.findByRole('form', { name: /Отклик на вакансию/ })
    await user.type(within(form).getByLabelText(/ФИО/), 'Асанов Бакыт')
    await user.type(within(form).getByLabelText(/Телефон/), '+996 555 123 456')
    await user.type(within(form).getByLabelText(/Электронная почта/), 'bakyt@mail.kg')
    await user.click(within(form).getByLabelText(/Я согласен/))
    await user.click(within(form).getByRole('button', { name: 'Отправить заявку' }))
    expect(await within(form).findByText('Введите правильный адрес электронной почты.')).toBeInTheDocument()
    await user.click(within(form).getByRole('button', { name: 'Отправить заявку' }))
    expect(await within(form).findByText(/Вы уже откликнулись/)).toBeInTheDocument()
    expect(api.apply.mock.calls[0][1].submission_token).toBe(api.apply.mock.calls[1][1].submission_token)
  })
})

describe('проверка формы отклика', () => {
  const base = { full_name: 'Асанов Бакыт', phone: '+996 555 123 456', email: 'b@mail.kg', city: '', experience: '', education: '', skills: '',
    cover_letter: '', portfolio_url: '', source: '', consent: true, website: '', resume: null }

  it('формат и размер резюме, ссылка на портфолио', () => {
    expect(validateApply(base, 5)).toEqual({})
    expect(validateApply({ ...base, resume: new File(['x'], 'cv.exe') }, 5).resume).toBe('Резюме — только в формате PDF или DOCX.')
    const big = new File(['x'], 'cv.pdf')
    Object.defineProperty(big, 'size', { value: 6 * 1024 * 1024 })
    expect(validateApply({ ...base, resume: big }, 5).resume).toBe('Файл больше 5 МБ.')
    expect(validateApply({ ...base, portfolio_url: 'javascript:alert(1)' }, 5).portfolio_url).toBeTruthy()
    expect(validateApply({ ...base, phone: '12' }, 5).phone).toBe('Проверьте номер телефона.')
    expect(validateApply({ ...base, email: 'bad' }, 5).email).toBe('Проверьте адрес электронной почты.')
  })
})
