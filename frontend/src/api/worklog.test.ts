import MockAdapter from 'axios-mock-adapter'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/api/client'
import { worklogApi } from '@/api/worklog'

describe('worklogApi.downloadReportPdf', () => {
  const mock = new MockAdapter(apiClient)
  afterEach(() => {
    mock.reset()
    vi.restoreAllMocks()
  })

  it('saves the PDF under the server file name', async () => {
    mock.onGet('/worklog/reports/5/pdf/').reply(200, new Blob(['%PDF-1.4']), {
      'content-disposition': 'attachment; filename="teamlead_report_monthly_2026_09.pdf"',
    })
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await expect(worklogApi.downloadReportPdf(5)).resolves.toBe('teamlead_report_monthly_2026_09.pdf')
    expect(click).toHaveBeenCalled()
  })

  it('surfaces the JSON error hidden in a blob response', async () => {
    mock.onGet('/worklog/reports/5/pdf/').reply(403, new Blob([JSON.stringify({ detail: 'Нет доступа' })], { type: 'application/json' }))
    await expect(worklogApi.downloadReportPdf(5)).rejects.toMatchObject({ response: { data: { detail: 'Нет доступа' } } })
  })
})
