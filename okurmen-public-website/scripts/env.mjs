/** Build-time env: process.env plus the Vite .env files (same precedence as Vite: real env wins). */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { SITE_ORIGIN } from '../src/seo/core.js'

export function loadEnv() {
  const env = { ...process.env }
  for (const file of ['.env', '.env.production', '.env.local', '.env.production.local']) {
    const path = resolve(file)
    if (!existsSync(path)) continue
    for (const line of readFileSync(path, 'utf8').split('\n')) {
      const match = line.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/)
      if (match && env[match[1]] === undefined) env[match[1]] = match[2].replace(/^['"]|['"]$/g, '')
    }
  }
  return {
    /** The canonical origin — https://www.okurmenkids.com unless VITE_SITE_URL overrides it. */
    site: (env.VITE_SITE_URL || SITE_ORIGIN).trim().replace(/\/+$/, ''),
    api: (env.VITE_API_URL || '').trim().replace(/\/+$/, ''),
  }
}

export async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(15000) })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`)
  return response.json()
}
