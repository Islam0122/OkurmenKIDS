import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const manifest = JSON.parse(readFileSync(join(process.cwd(), 'public/manifest.webmanifest'), 'utf8'))
const indexHtml = readFileSync(join(process.cwd(), 'index.html'), 'utf8')

describe('manifest — the installed app starts at the public portal', () => {
  it('launches into /portal with the whole site in scope', () => {
    expect(manifest.start_url).toBe('/portal')
    expect(manifest.scope).toBe('/')
    expect(manifest.display).toBe('standalone')
  })

  it('keeps its identity, so existing installs update instead of duplicating', () => {
    expect(manifest.id).toBe('/')
  })

  it('is white, and the page does not override the title bar with another colour', () => {
    expect(manifest.background_color.toLowerCase()).toBe('#ffffff')
    expect(manifest.theme_color.toLowerCase()).toBe('#ffffff')
    expect(indexHtml).toContain('<meta name="theme-color" content="#ffffff" />')
  })

  it('ships the official logo at 192 and 512', () => {
    const sizes = manifest.icons.map((icon: { sizes: string }) => icon.sizes)
    expect(sizes).toEqual(expect.arrayContaining(['192x192', '512x512']))
  })
})
