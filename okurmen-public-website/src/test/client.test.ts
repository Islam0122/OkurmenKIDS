import { AxiosError, AxiosHeaders } from 'axios'

import { toApiError } from '@/services/api/client'
import { mediaUrl } from '@/utils/media'

const err = (status: number, data: unknown) =>
  new AxiosError('x', 'ERR', undefined, undefined, { status, data, statusText: '', headers: {}, config: { headers: new AxiosHeaders() } })

describe('api client', () => {
  it('maps HTTP errors', () => {
    expect(toApiError(err(404, { detail: 'nope' })).kind).toBe('not_found')
    expect(toApiError(err(429, {})).kind).toBe('rate_limited')
    expect(toApiError(err(400, { phone: ['bad'] })).fields).toEqual({ phone: ['bad'] })
    expect(toApiError(new AxiosError('down')).kind).toBe('network')
  })

  it('serves backend media from the API origin', () => {
    expect(mediaUrl('/media/news/a.webp')).toBe('http://api.test/media/news/a.webp')
    expect(mediaUrl('https://cdn.kg/a.png')).toBe('https://cdn.kg/a.png')
  })
})
