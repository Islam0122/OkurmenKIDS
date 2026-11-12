import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { withHydrateFallback } from './index'

describe('первая загрузка lazy-маршрута (прямой адрес / обновление страницы)', () => {
  it('показывает загрузку вместо пустого экрана и не пишет предупреждение HydrateFallback', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    let resolve!: () => void
    const ready = new Promise<void>((r) => { resolve = r })
    const router = createMemoryRouter(withHydrateFallback([
      { path: '/marketing/site', children: [{ index: true, lazy: async () => { await ready; return { Component: () => <h1>Обзор сайта</h1> } } }] },
    ]), { initialEntries: ['/marketing/site'] })
    render(<RouterProvider router={router} />)
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка')
    resolve()
    expect(await screen.findByRole('heading', { name: 'Обзор сайта' })).toBeInTheDocument()
    expect(warn.mock.calls.flat().join(' ')).not.toMatch(/HydrateFallback/)
  })
})
