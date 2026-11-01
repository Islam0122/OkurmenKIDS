import { describe, expect, it } from 'vitest'

import { parseReportPeriod, reportPeriodOptions, reportPeriodParams, withReportPeriod } from './reportPeriod'

describe('reportPeriod', () => {
  it('sends a concrete month as its exact date range', () => {
    expect(reportPeriodParams('2026-09')).toEqual({ period: 'custom', start_date: '2026-09-01', end_date: '2026-09-30' })
    expect(reportPeriodParams('2026-10')).toEqual({ period: 'custom', start_date: '2026-10-01', end_date: '2026-10-31' })
    expect(reportPeriodParams('2028-02')).toEqual({ period: 'custom', start_date: '2028-02-01', end_date: '2028-02-29' })
    expect(reportPeriodParams('this_month')).toEqual({ period: 'this_month' })
  })

  it('parses only presets and valid months from the URL', () => {
    expect(parseReportPeriod('2026-09')).toBe('2026-09')
    expect(parseReportPeriod('last_month')).toBe('last_month')
    for (const bad of [null, '', '2026-13', '2026-9', 'custom', 'decade']) {
      expect(parseReportPeriod(bad)).toBeNull()
    }
  })

  it('offers September and October 2026 as months of their own', () => {
    const options = reportPeriodOptions(new Date(2026, 10, 1))
    const labels = Object.fromEntries(options.map((o) => [o.value, o.label]))
    expect(labels['this_month']).toBe('Этот месяц (Ноябрь 2026)')
    expect(labels['last_month']).toBe('Прошлый месяц (Октябрь 2026)')
    expect(labels['2026-10']).toBe('Октябрь 2026')
    expect(labels['2026-09']).toBe('Сентябрь 2026')
    expect(labels['2025-11']).toBe('Ноябрь 2025')
    // A month from a link older than the list is still shown, not swapped for another.
    expect(reportPeriodOptions(new Date(2026, 10, 1), '2024-05').at(-1)).toEqual({ value: '2024-05', label: 'Май 2024' })
  })

  it('carries a non-default period into links', () => {
    expect(withReportPeriod('/app/trainers/3', '2026-09')).toBe('/app/trainers/3?period=2026-09')
    expect(withReportPeriod('/app/trainers/3', 'this_month')).toBe('/app/trainers/3')
  })
})
