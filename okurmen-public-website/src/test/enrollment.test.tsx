import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { createQueryClient } from '@/app/providers/AppProviders'
import { EnrollmentForm } from '@/features/enrollment/EnrollmentForm'
import { I18nProvider } from '@/i18n'
import { ApiError } from '@/services/api/client'
import { siteApi } from '@/services/endpoints'

vi.mock('@/services/endpoints', () => ({
  siteApi: {
    courses: vi.fn().mockResolvedValue({ results: [{ slug: 'python', title: 'Python' }] }),
    settings: vi.fn().mockResolvedValue({ branches: [], contacts: {} }),
    lead: vi.fn(),
  },
}))

function setup() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/courses/python']}>
        <I18nProvider lang="ru">
          <EnrollmentForm defaultCourse="python" />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

describe('EnrollmentForm', () => {
  beforeEach(() => {
    vi.mocked(siteApi.lead).mockReset()
  })

  it('validates before sending', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))
    expect(await screen.findByText('Укажите имя (минимум 2 буквы)')).toBeInTheDocument()
    expect(screen.getByText('Заполните это поле')).toBeInTheDocument()
    expect(siteApi.lead).not.toHaveBeenCalled()
  })

  it('sends a valid lead once and shows success', async () => {
    vi.mocked(siteApi.lead).mockResolvedValue({ ok: true, duplicate: false })
    const user = setup()
    await user.type(screen.getByLabelText('Имя родителя'), 'Айгуль')
    await user.type(screen.getByLabelText('Телефон'), '0555 123 456')
    await user.type(screen.getByLabelText('Возраст ребёнка'), '10')
    await waitFor(() => expect(screen.getByLabelText(/Курс/)).toHaveValue('python'))
    const submit = screen.getByRole('button', { name: 'Отправить заявку' })
    await user.click(submit)
    expect(await screen.findByText('Спасибо! Заявка отправлена')).toBeInTheDocument()
    expect(siteApi.lead).toHaveBeenCalledTimes(1)
    expect(vi.mocked(siteApi.lead).mock.calls[0][0]).toMatchObject({ parent_name: 'Айгуль', child_age: 10, course: 'python', contact_method: 'whatsapp', language: 'ru', source: '/courses/python' })
  })

  it('shows server field errors', async () => {
    vi.mocked(siteApi.lead).mockImplementation(async () => { throw new ApiError('validation', 400, 'bad', { phone: ['Проверьте номер телефона.'] }) })
    const user = setup()
    await user.type(screen.getByLabelText('Имя родителя'), 'Айгуль')
    await user.type(screen.getByLabelText('Телефон'), '0555 123 456')
    await user.type(screen.getByLabelText('Возраст ребёнка'), '10')
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))
    expect(await screen.findByText('Проверьте номер телефона.')).toBeInTheDocument()
  })
})
