/**
 * Runtime configuration — only from environment variables (never hardcoded
 * URLs). See .env.example.
 */
import { SITE_ORIGIN } from '@/seo/core'

const trim = (value: string | undefined) => (value ?? '').trim().replace(/\/+$/, '')

export const env = {
  /** The existing Django LMS backend, e.g. https://okurmenkids.up.railway.app */
  apiUrl: trim(import.meta.env.VITE_API_URL),
  /** Where /media/... uploads are served from (defaults to the API origin). */
  mediaUrl: trim(import.meta.env.VITE_MEDIA_URL) || trim(import.meta.env.VITE_API_URL),
  /** This website's canonical origin (https://www.okurmenkids.com unless VITE_SITE_URL says otherwise) — canonical URLs, hreflang, Open Graph. Never the current host, so preview and *.vercel.app copies point to the real site. */
  siteUrl: trim(import.meta.env.VITE_SITE_URL) || SITE_ORIGIN,
  /** The academy's careers site (apps.recruitment, served by the LMS frontend at /careers). Empty = no «join the team» CTA. */
  careersUrl: trim(import.meta.env.VITE_CAREERS_URL ?? 'https://okurmen-kids-drab.vercel.app/careers'),
  /** Demo content for UI development only. Every page shows a banner while on. */
  useMocks: import.meta.env.VITE_USE_MOCKS === 'true',
} as const

export const isConfigured = Boolean(env.apiUrl) || env.useMocks
