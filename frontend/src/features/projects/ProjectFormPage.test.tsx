import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'

import { ProjectFormPage } from './ProjectFormPage'
import { buildOptions, buildProjectDetail } from './projectFixtures'

vi.mock('@/api/projects', () => ({
  projectsApi: {
    options: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(),
    uploadImage: vi.fn(), setCover: vi.fn(), removeImage: vi.fn(),
  },
}))

import { projectsApi } from '@/api/projects'

function renderForm(route = '/trainer/projects/new') {
  return renderWithProviders(
    <Routes>
      <Route path="/trainer/projects/new" element={<ProjectFormPage />} />
      <Route path="/trainer/projects/:id/edit" element={<ProjectFormPage />} />
      <Route path="/trainer/projects/:id" element={<p>detail page</p>} />
    </Routes>,
    { route },
  )
}

describe('ProjectFormPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(projectsApi.options).mockResolvedValue(buildOptions())
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview')
    globalThis.URL.revokeObjectURL = vi.fn()
  })

  it('validates required fields before calling the API', async () => {
    const user = userEvent.setup()
    renderForm()
    await user.click(await screen.findByRole('button', { name: 'Опубликовать проект' }))
    expect(await screen.findByText('Выберите студента.')).toBeInTheDocument()
    expect(screen.getByText('Укажите название проекта.')).toBeInTheDocument()
    expect(projectsApi.create).not.toHaveBeenCalled()
  })

  it('picks a student (group fills itself), uploads images and publishes', async () => {
    const user = userEvent.setup()
    vi.mocked(projectsApi.create).mockResolvedValue(buildProjectDetail({ id: 42 }))
    vi.mocked(projectsApi.uploadImage).mockImplementation(async (_id, _file, _cover, onProgress) => {
      onProgress?.(100)
      return { id: 900, url: '/media/x.png', is_cover: true, order: 1 }
    })
    renderForm()

    const combo = await screen.findByRole('combobox')
    await user.click(combo)
    await user.type(combo, 'бекз')
    await user.keyboard('{Enter}')
    expect(screen.getByLabelText(/^Группа/)).toHaveValue('JUNIOR 2')

    await user.type(screen.getByLabelText(/^Название проекта/), 'Игра на Scratch')
    await user.type(screen.getByLabelText(/^Технологии/), 'Scratch{Enter}')

    const file = new File(['png'], 'shot.png', { type: 'image/png' })
    await user.upload(screen.getByLabelText(/Выберите файлы/), file)
    expect(screen.getByText('Обложка')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Опубликовать проект' }))

    await waitFor(() => expect(projectsApi.create).toHaveBeenCalled())
    expect(vi.mocked(projectsApi.create).mock.calls[0][0]).toMatchObject({
      student: 8, title: 'Игра на Scratch', technologies: ['Scratch'], status: 'published',
    })
    expect(projectsApi.uploadImage).toHaveBeenCalledWith(42, file, true, expect.any(Function))
    expect(await screen.findByText('detail page')).toBeInTheDocument()
  })

  it('rejects unsupported image types', async () => {
    const user = userEvent.setup({ applyAccept: false })
    renderForm()
    await screen.findByRole('combobox')
    await user.upload(screen.getByLabelText(/Выберите файлы/), new File(['gif'], 'anim.gif', { type: 'image/gif' }))
    expect(screen.getByText('«anim.gif» — поддерживаются только JPG, PNG и WEBP.')).toBeInTheDocument()
  })

  it('shows server field errors', async () => {
    const user = userEvent.setup()
    const { AxiosError } = await import('axios')
    const error = new AxiosError('bad', '400', undefined, undefined, {
      status: 400, data: { github_url: ['Введите правильный URL.'] }, statusText: '', headers: {}, config: {} as never,
    })
    vi.mocked(projectsApi.update).mockRejectedValue(error)
    vi.mocked(projectsApi.get).mockResolvedValue(buildProjectDetail({ id: 5 }))
    renderForm('/trainer/projects/5/edit')

    expect(await screen.findByDisplayValue('Приложение погоды')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Сохранить черновик' }))
    expect(await screen.findByText('Введите правильный URL.')).toBeInTheDocument()
    expect(vi.mocked(projectsApi.update).mock.calls[0][1]).toMatchObject({ status: 'draft' })
  })
})
