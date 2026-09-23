import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { buildTeacher } from '@/test/fixtures'
import type { MonthlyTeacherReport } from '@/types/monthlyReport'

import { ReportHeader } from './ReportHeader'

vi.mock('@/api/client', () => ({ API_BASE_URL: 'https://okurmen-api.up.railway.app/api/v1' }))

function reportFor(image: string | null): MonthlyTeacherReport {
  // ReportHeader only reads teacher/year/month.
  return { teacher: buildTeacher({ image }), year: 2026, month: 9 } as MonthlyTeacherReport
}

describe('ReportHeader photo', () => {
  it('loads a root-relative photo from the API origin', () => {
    render(<ReportHeader report={reportFor('/media/teachers/avatar.png')} />)
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://okurmen-api.up.railway.app/media/teachers/avatar.png',
    )
  })

  it('keeps an absolute photo URL as is', () => {
    const absolute = 'https://okurmen-api.up.railway.app/media/teachers/avatar.png'
    render(<ReportHeader report={reportFor(absolute)} />)
    expect(screen.getByRole('img')).toHaveAttribute('src', absolute)
  })

  it('shows initials when there is no photo', () => {
    render(<ReportHeader report={reportFor(null)} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
