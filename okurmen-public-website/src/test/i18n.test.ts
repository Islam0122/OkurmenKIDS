import { localizedPath, splitLangPath, translate } from '@/i18n'
import { en } from '@/i18n/locales/en'
import { ky } from '@/i18n/locales/ky'
import { ru } from '@/i18n/locales/ru'

describe('i18n', () => {
  it('every language has every key, none empty', () => {
    for (const dict of [ky, en]) {
      expect(Object.keys(dict).sort()).toEqual(Object.keys(ru).sort())
      expect(Object.entries(dict).filter(([, v]) => !v.trim())).toEqual([])
    }
  })

  it('localizes paths and splits them back', () => {
    expect(localizedPath('ru', '/courses')).toBe('/courses')
    expect(localizedPath('ky', '/')).toBe('/ky')
    expect(localizedPath('en', '/news/a')).toBe('/en/news/a')
    expect(splitLangPath('/ky/courses/python')).toEqual({ lang: 'ky', rest: '/courses/python' })
    expect(splitLangPath('/kyiv')).toEqual({ lang: 'ru', rest: '/kyiv' })
  })

  it('interpolates variables', () => {
    expect(translate('en')('courses.ageRange', { from: 8, to: 12 })).toBe('8–12 years')
  })
})

describe('Kyrgyz dates without browser support', () => {
  it('matches the ICU ky format', async () => {
    const { formatKyrgyz } = await import('@/i18n/dates')
    const d = new Date(2026, 10, 14, 6, 29)
    expect(formatKyrgyz(d, { day: 'numeric', month: 'long', year: 'numeric' })).toBe('2026-ж., 14-ноябрь')
    expect(formatKyrgyz(d, { day: 'numeric', month: 'short', year: 'numeric' })).toBe('2026-ж. 14-ноя.')
    expect(formatKyrgyz(d, { weekday: 'long', day: 'numeric', month: 'long' })).toBe('14-ноябрь, ишемби')
    expect(formatKyrgyz(d, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })).toBe('14-ноябрь 06:29')
    expect(formatKyrgyz(d, { month: 'short' })).toBe('Ноя')
    expect(formatKyrgyz(d, { hour: '2-digit', minute: '2-digit' })).toBe('06:29')
  })
})
