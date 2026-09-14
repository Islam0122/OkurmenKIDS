import { describe, expect, it } from 'vitest'

import { attendanceUrlFor, homeworkUrlFor, isSafeInternalPath, resolveReturnTo } from './returnTo'

describe('isSafeInternalPath', () => {
  it('accepts a plain internal path', () => {
    expect(isSafeInternalPath('/app/lessons/7')).toBe(true)
    expect(isSafeInternalPath('/app/lessons?view=today&date=2026-09-14')).toBe(true)
  })

  it.each([
    [null],
    [undefined],
    [''],
    ['app/lessons/7'], // no leading slash
    ['//evil.com/phishing'], // protocol-relative — browsers treat this as https://evil.com
    ['https://evil.com'],
    ['http://evil.com/app/lessons/7'],
    ['javascript:alert(1)'],
    // Conservative on purpose: a `://` anywhere (even buried in a query
    // value) is rejected rather than parsed apart, since this app never
    // needs one in a legitimate return path.
    ['/redirect?to=https://evil.com'],
  ])('rejects unsafe or empty candidate %p', (value) => {
    expect(isSafeInternalPath(value)).toBe(false)
  })
})

describe('resolveReturnTo', () => {
  it('returns the candidate when it is a safe internal path', () => {
    expect(resolveReturnTo('/app/lessons/7', '/app/attendance')).toBe('/app/lessons/7')
  })

  it('falls back for a missing candidate', () => {
    expect(resolveReturnTo(null, '/app/attendance')).toBe('/app/attendance')
    expect(resolveReturnTo(undefined, '/app/attendance')).toBe('/app/attendance')
    expect(resolveReturnTo('', '/app/attendance')).toBe('/app/attendance')
  })

  it('falls back instead of ever handing back an external URL', () => {
    expect(resolveReturnTo('https://evil.com', '/app/attendance')).toBe('/app/attendance')
    expect(resolveReturnTo('//evil.com', '/app/attendance')).toBe('/app/attendance')
  })
})

describe('attendanceUrlFor', () => {
  it('builds a URL carrying both the lesson id and the return path', () => {
    const url = attendanceUrlFor(7, '/app/lessons/7')
    const parsed = new URL(url, 'https://app.local')
    expect(parsed.pathname).toBe('/app/attendance')
    expect(parsed.searchParams.get('lesson')).toBe('7')
    expect(parsed.searchParams.get('returnTo')).toBe('/app/lessons/7')
  })
})

describe('homeworkUrlFor', () => {
  it('builds a URL to the homework detail page carrying the return path', () => {
    const url = homeworkUrlFor(55, '/app/lessons/7')
    const parsed = new URL(url, 'https://app.local')
    expect(parsed.pathname).toBe('/app/homework/55')
    expect(parsed.searchParams.get('returnTo')).toBe('/app/lessons/7')
  })
})
