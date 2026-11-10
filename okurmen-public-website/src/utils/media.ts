import { env } from '@/app/config/env'

/** Backend media paths are relative (/media/...): serve them from the API / media origin. */
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined
  if (/^(https?:|data:|blob:)/.test(path)) return path
  if (path.startsWith('/media/') || path.startsWith('media/')) return `${env.mediaUrl}/${path.replace(/^\//, '')}`
  return path
}

export function absoluteUrl(path: string): string {
  if (/^https?:/.test(path)) return path
  return `${env.siteUrl}${path.startsWith('/') ? '' : '/'}${path}`
}
