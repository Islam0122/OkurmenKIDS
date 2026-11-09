import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HOME_PATH } from '@/lib/appMode'
import { renderWithProviders } from '@/test/testUtils'

import { RootRedirect } from './RootRedirect'

function displayMode(standalone: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: standalone && query === '(display-mode: standalone)',
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

function renderRoot() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/portal" element={<div>Public portal</div>} />
      <Route path={HOME_PATH} element={<div>Build home</div>} />
    </Routes>,
    { route: '/' },
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('RootRedirect («/»)', () => {
  it('opens the public portal in the installed app (old installs launch at «/»)', () => {
    displayMode(true)
    renderRoot()
    expect(screen.getByText('Public portal')).toBeInTheDocument()
  })

  it('keeps the build home in a browser tab', () => {
    displayMode(false)
    renderRoot()
    expect(screen.getByText('Build home')).toBeInTheDocument()
  })
})
