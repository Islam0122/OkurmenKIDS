import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, vi } from 'vitest'

import { AppRoutes } from '@/App'
import { groupByCategory } from '@/lib/categories'
import { routeFetch } from '@/test/testBackend'
import type { TrainingTest } from '@/types'

afterEach(() => vi.restoreAllMocks())

const IT = { id: 1, name: 'IT', slug: 'it' }
const EN = { id: 2, name: 'English', slug: 'english' }
function trainer(id: string, title: string, category: TrainingTest['category']): TrainingTest {
  return {
    id, title, category, description: 'Даярдык', subject: category?.name ?? '', level: 'easy', level_display: 'Жеңил',
    image_url: null, duration: 20, questions_count: 10, max_attempts: null, passing_score: 60, show_explanation: true,
    show_result: true, allow_retry: true, course: '', exam_url: '', published: true,
    security: { require_fullscreen: false, track_tab_switches: true, max_tab_switches: null, block_copy_paste: true },
  }
}
// The backend's order: categories, then naturally sorted titles, uncategorised last.
const TESTS = [trainer('a', 'IT Month 1', IT), trainer('b', 'IT Month 2', IT), trainer('c', 'English Month 1', EN), trainer('d', 'Intro', null)]

describe('training list by category', () => {
  it('groups by the category the backend sends, in its order, uncategorised last', () => {
    const groups = groupByCategory([TESTS[0], TESTS[3], TESTS[2], TESTS[1]])
    expect(groups.map((g) => g.category?.name ?? null)).toEqual(['IT', 'English', null])
    expect(groups[0].tests.map((x) => x.title)).toEqual(['IT Month 1', 'IT Month 2'])
  })

  it('renders a section per category with compact cards and filters by category', async () => {
    const user = userEvent.setup()
    routeFetch({ 'GET /portal/': () => ({ body: { hero_title: '', hero_subtitle: '', start_button_label: '', exam_button_label: '', exam_url: '', exam_open_in_new_tab: false } }),
      'GET /tests/': () => ({ body: TESTS }) })
    render(<MemoryRouter initialEntries={['/training']}><AppRoutes /></MemoryRouter>)

    const it = await screen.findByRole('region', { name: 'IT' })
    expect(within(it).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['IT', 'IT Month 1', 'IT Month 2'])
    expect(within(it).getByText('2 тест')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'English' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Башка' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /English/ }))
    expect(screen.queryByRole('region', { name: 'IT' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'English' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Баары' }))
    expect(screen.getByRole('region', { name: 'IT' })).toBeInTheDocument()
  })
})
