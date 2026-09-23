import { describe, expect, it } from 'vitest'

import { resolveMediaUrl } from './mediaUrl'

const RAILWAY_API = 'https://okurmen-api.up.railway.app/api/v1'

describe('resolveMediaUrl', () => {
  it.each([[null], [undefined], ['']])('returns null for an empty value %p', (value) => {
    expect(resolveMediaUrl(value, RAILWAY_API)).toBeNull()
  })

  it('resolves a root-relative media path against the API origin, not the SPA origin', () => {
    expect(resolveMediaUrl('/media/teachers/avatar.png', RAILWAY_API)).toBe(
      'https://okurmen-api.up.railway.app/media/teachers/avatar.png',
    )
  })

  it('keeps the API origin port and drops the API path prefix', () => {
    expect(resolveMediaUrl('/media/teachers/a.png', 'http://localhost:8000/api/v1/')).toBe(
      'http://localhost:8000/media/teachers/a.png',
    )
  })

  it('stays same-origin when the API base is relative (dev, Vite proxies /media)', () => {
    expect(resolveMediaUrl('/media/teachers/a.png', '/api/v1')).toBe(
      `${window.location.origin}/media/teachers/a.png`,
    )
  })

  it('preserves an encoded file name', () => {
    expect(resolveMediaUrl('/media/teachers/%D1%84%D0%BE%D1%82%D0%BE.png', RAILWAY_API)).toBe(
      'https://okurmen-api.up.railway.app/media/teachers/%D1%84%D0%BE%D1%82%D0%BE.png',
    )
  })

  it.each([
    ['https://okurmen-api.up.railway.app/media/teachers/a.png'],
    ['http://localhost:8000/media/teachers/a.png'],
    ['https://cdn.example.com/teachers/a.png?X-Amz-Signature=abc'],
    ['//cdn.example.com/teachers/a.png'],
    ['data:image/png;base64,iVBORw0KGgo='],
    ['blob:http://localhost/1234'],
  ])('returns an already absolute URL unchanged %p', (value) => {
    expect(resolveMediaUrl(value, RAILWAY_API)).toBe(value)
  })
})
