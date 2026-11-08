import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError, type AxiosResponse } from 'axios'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NewsArticle, NewsCard, NewsPage as NewsPageData } from '@/api/publicNews'
import { renderWithProviders } from '@/test/testUtils'

import { ArticlePage } from './ArticlePage'
import { parseBody } from './ArticleBody'
import { NewsPage } from './NewsPage'

vi.mock('@/api/publicNews', async (original) => {
  const actual = await original<typeof import('@/api/publicNews')>()
  return { ...actual, publicNewsApi: { list: vi.fn(), article: vi.fn() } }
})
vi.mock('@/api/client', async (original) => {
  const actual = await original<typeof import('@/api/client')>()
  const fail = () => { throw new Error('public news used the authenticated API client') }
  return { ...actual, apiClient: { get: fail, post: fail, put: fail, patch: fail, delete: fail } }
})
const mockUseAuth = vi.fn()
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => mockUseAuth() }))

import { publicNewsApi } from '@/api/publicNews'

const api = vi.mocked(publicNewsApi)
const image = (name: string, caption = '', width = 1600, height = 1067) => ({ url: `/media/news/${name}.webp`, thumb: `/media/news/${name}-t.webp`, width, height, caption })

function item(over: Partial<NewsCard> = {}): NewsCard {
  return { slug: 'robotics-cup', title: 'Robotics Cup 2026', excerpt: 'Our team won the cup', category: 'competitions',
    published_at: '2026-11-05T10:00:00+06:00', cover: image('cover'), photo_count: 4, ...over }
}

function page(results: NewsCard[], over: Partial<NewsPageData> = {}): NewsPageData {
  return { count: results.length, page: 1, page_size: 9, num_pages: 1, featured: null, results,
    counts: { all: results.length, events: 0, achievements: 0, competitions: results.length, education: 0, announcements: 0, activities: 0 }, ...over }
}

function render(route = '/news') {
  return renderWithProviders(
    <Routes>
      <Route path="/news" element={<NewsPage />} />
      <Route path="/news/:slug" element={<ArticlePage />} />
      <Route path="/login" element={<div>Login page</div>} />
    </Routes>,
    { route },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mockUseAuth.mockReturnValue({ user: null, status: 'guest', logout: vi.fn() })
})

describe('public Academy News', () => {
  it('shows the featured story and the grid to a guest, no login', async () => {
    api.list.mockResolvedValue(page([item({ slug: 'open-day', title: 'Open Day', category: 'events' })], { featured: item() }))
    render()
    expect(screen.getByRole('heading', { level: 1, name: 'Academy News' })).toBeInTheDocument()
    const featured = await screen.findByRole('link', { name: /Robotics Cup 2026/ })
    expect(featured).toHaveAttribute('href', '/news/robotics-cup')
    expect(within(featured).getByText('Featured')).toBeInTheDocument()
    expect(within(featured).getByText('Competitions')).toBeInTheDocument()
    expect(within(featured).getByText('Read More')).toBeInTheDocument()
    expect(within(featured).getByText('5 November 2026')).toBeInTheDocument()
    const card = screen.getByRole('link', { name: /Open Day/ })
    expect(within(card).getByText('Academy Events')).toBeInTheDocument()
    expect(within(card).getByText('4 photos')).toBeInTheDocument()
    expect(card.querySelector('img')).toHaveAttribute('loading', 'lazy')
    expect(card.querySelector('img')?.getAttribute('srcset')).toContain('640w')
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/portal')
  })

  it('filters by category and searches', async () => {
    api.list.mockResolvedValue(page([item()]))
    render()
    await screen.findByText('Robotics Cup 2026')
    await userEvent.click(screen.getByRole('button', { name: /^Student Achievements/ }))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'achievements' })))
    await userEvent.type(screen.getByLabelText('Search news'), 'robot')
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'achievements', q: 'robot' })))
  })

  it('has empty, no-results and error states', async () => {
    api.list.mockResolvedValue(page([]))
    const view = render()
    expect(await screen.findByText('No news yet')).toBeInTheDocument()
    view.unmount()

    render('/news?category=education')
    expect(await screen.findByText('Nothing found')).toBeInTheDocument()
  })

  it('retries after an error', async () => {
    api.list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(page([item()]))
    render()
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Robotics Cup 2026')).toBeInTheDocument()
  })
})

describe('public news article', () => {
  const article: NewsArticle = {
    slug: 'robotics-cup', title: 'Robotics Cup 2026', excerpt: 'Our team won the cup', category: 'competitions',
    published_at: '2026-11-05T10:00:00+06:00', author: null,
    body: 'First paragraph.\n\n## How it went\n- Round one\n- Round two\n\nLast paragraph.',
    cover: image('cover', 'Winners on stage'),
    photos: [image('p1', 'The team', 900, 1200), image('p2', '', 1600, 900)],
    related: [item({ slug: 'open-day', title: 'Open Day', category: 'events' })],
  }

  it('shows the article, gallery with captions, lightbox, share and related news', async () => {
    api.article.mockResolvedValue(article)
    render('/news/robotics-cup')
    expect(await screen.findByRole('heading', { level: 1, name: 'Robotics Cup 2026' })).toBeInTheDocument()
    expect(api.article).toHaveBeenCalledWith('robotics-cup')
    expect(screen.getByText('Winners on stage')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How it went' })).toBeInTheDocument()
    expect(screen.getByText('Round two')).toBeInTheDocument()
    expect(screen.getByText('The team')).toBeInTheDocument()
    expect(screen.queryByText('Author')).not.toBeInTheDocument()
    expect(document.title).toBe('OkurmenKids Digital — Robotics Cup 2026')

    await userEvent.click(screen.getByRole('button', { name: 'Enlarge photo 2: The team' }))
    const viewer = screen.getByRole('dialog', { name: 'Photo 2 of 3' })
    expect(within(viewer).getByText('The team')).toBeInTheDocument()
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('dialog', { name: 'Photo 3 of 3' })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    expect(screen.getByRole('link', { name: 'Telegram' }).getAttribute('href')).toContain('t.me/share')
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open Day/ })).toHaveAttribute('href', '/news/open-day')
  })

  it('shows the author only when the API publishes it', async () => {
    api.article.mockResolvedValue({ ...article, author: 'Айгерим Токтогулова' })
    render('/news/robotics-cup')
    expect(await screen.findByText('Айгерим Токтогулова')).toBeInTheDocument()
  })

  it('says «not found» for drafts and unknown links', async () => {
    api.article.mockRejectedValue(new AxiosError('nf', 'ERR', undefined, undefined, { status: 404, data: {} } as AxiosResponse))
    render('/news/secret-draft')
    expect(await screen.findByText('Article not found')).toBeInTheDocument()
  })
})

describe('article text', () => {
  it('turns plain text into paragraphs, headings and lists — never HTML', () => {
    expect(parseBody('One\ntwo\n\n## Head\n- a\n- b\n\n<b>x</b>')).toEqual([
      { kind: 'p', text: 'One\ntwo' }, { kind: 'h', text: 'Head' }, { kind: 'ul', items: ['a', 'b'] }, { kind: 'p', text: '<b>x</b>' },
    ])
  })
})
