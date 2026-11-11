/**
 * Runtime configuration — only from environment variables (never hardcoded
 * URLs). See .env.example.
 */
const trim = (value: string | undefined) => (value ?? '').trim().replace(/\/+$/, '')

export const env = {
  /** The existing Django LMS backend, e.g. https://okurmenkids.up.railway.app */
  apiUrl: trim(import.meta.env.VITE_API_URL),
  /** Where /media/... uploads are served from (defaults to the API origin). */
  mediaUrl: trim(import.meta.env.VITE_MEDIA_URL) || trim(import.meta.env.VITE_API_URL),
  /** This website's public origin — canonical URLs and Open Graph. */
  siteUrl: trim(import.meta.env.VITE_SITE_URL) || (typeof window !== 'undefined' ? window.location.origin : ''),
  /** Demo content for UI development only. Every page shows a banner while on. */
  useMocks: import.meta.env.VITE_USE_MOCKS === 'true',
} as const

export const isConfigured = Boolean(env.apiUrl) || env.useMocks
