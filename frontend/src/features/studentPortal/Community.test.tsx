import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/testUtils'
import type { CommunityPost } from '@/types/community'
import type { PortalMe, PortalStudent } from '@/types/studentPortal'

vi.mock('@/api/studentPortal', () => ({ studentPortalApi: { me: vi.fn() } }))
vi.mock('@/api/community', () => ({
  communityApi: {
    summary: vi.fn(), feed: vi.fn(), mine: vi.fn(), post: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), like: vi.fn(),
    comments: vi.fn(), comment: vi.fn(), deleteComment: vi.fn(), reportPost: vi.fn(), reportComment: vi.fn(), profile: vi.fn(),
    notifications: vi.fn(), readNotifications: vi.fn(),
  },
  moderationApi: { meta: vi.fn(), posts: vi.fn(), act: vi.fn(), reports: vi.fn(), post: vi.fn(), announce: vi.fn(), closeReport: vi.fn(), hideComment: vi.fn(), removeAnnouncement: vi.fn() },
}))
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 9, role: 'student_parent', username: 'aibek.asanov' }, logout: vi.fn() }),
}))

import { communityApi, moderationApi } from '@/api/community'
import { studentPortalApi } from '@/api/studentPortal'
import { CommunityModerationPage } from '@/features/community/ModerationPage'

import { StudentPortalLayout } from './StudentPortalLayout'
import { StudentCommunityPage } from './pages/CommunityPage'
import { StudentCommunityProfilePage } from './pages/CommunityProfilePage'

const api = vi.mocked(communityApi)
const mod = vi.mocked(moderationApi)

function child(id: number, first: string): PortalStudent {
  return {
    id, first_name: first, last_name: 'Асанов', full_name: `${first} Асанов`, photo: null, birth_date: null, status: 'active',
    group: { id: 1, name: 'PRO-01' }, course: { id: 1, name: 'Python' }, branch: null, enrollment_date: '2026-09-01',
  }
}
const ME: PortalMe = { login: 'aibek.asanov', must_change_password: false, can_view_payments: true, students: [child(1, 'Айбек')] }

function post(id: number, extra: Partial<CommunityPost> = {}): CommunityPost {
  return {
    id, category: 'project', audience: 'academy', text: `Сделала игру «Змейка» #${id}`, project_url: 'https://github.com/bek/snake',
    status: 'approved', is_announcement: false, is_pinned: false, created_at: new Date().toISOString(),
    published_at: new Date().toISOString(), edited_at: null,
    author: { type: 'student', student_id: 2, name: 'Бек Бекова', first_name: 'Бек', group: { id: 1, name: 'PRO-01' }, photo: null },
    group: { id: 1, name: 'PRO-01' }, images: [], likes: 3, comments: 1, liked: false, mine: false, can_edit: false, can_delete: false,
    ...extra,
  }
}

function renderAt(path: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/student" element={<StudentPortalLayout />}>
        <Route path="community" element={<StudentCommunityPage />} />
        <Route path="community/u/:id" element={<StudentCommunityProfilePage />} />
      </Route>
    </Routes>,
    { route: path },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  vi.mocked(studentPortalApi.me).mockResolvedValue(ME)
  api.summary.mockResolvedValue({ published: 1, pending: 1, drafts: 0, rejected: 0, unread: 2, can_post: true })
  api.feed.mockResolvedValue({
    count: 1, next: null, previous: null, results: [post(10)],
    pinned: [post(11, { is_announcement: true, is_pinned: true, category: 'news', text: 'Хакатон в субботу!', project_url: '',
      author: { type: 'academy', student_id: null, name: 'Okurmen Kids', group: null, photo: null } })],
  })
  api.mine.mockResolvedValue({ count: 0, next: null, previous: null, results: [] })
})

describe('Student community', () => {
  it('shows approved posts with author, group, category, counts, and the pinned announcement first', async () => {
    renderAt('/student/community')
    const cards = await screen.findAllByRole('article')
    expect(within(cards[0]).getByText('Хакатон в субботу!')).toBeInTheDocument()
    expect(within(cards[0]).getByText('Официально')).toBeInTheDocument()
    expect(within(cards[1]).getByText('Бек Бекова')).toBeInTheDocument()
    expect(within(cards[1]).getByText(/PRO-01/)).toBeInTheDocument()
    expect(within(cards[1]).getByText('Проект')).toBeInTheDocument()
    expect(within(cards[1]).getByRole('link', { name: /Открыть проект · github.com/ })).toHaveAttribute('rel', 'noopener noreferrer nofollow')
    expect(within(cards[1]).getByRole('button', { name: 'Нравится' })).toHaveTextContent('3')
    expect(screen.getAllByRole('link', { name: /Сообщество/ }).length).toBeGreaterThan(0)   // in the navigation
  })

  it('likes and unlikes with the server count', async () => {
    api.like.mockResolvedValueOnce({ liked: true, likes: 4 }).mockResolvedValueOnce({ liked: false, likes: 3 })
    renderAt('/student/community')
    const card = (await screen.findAllByRole('article'))[1]
    await userEvent.click(within(card).getByRole('button', { name: 'Нравится' }))
    await waitFor(() => expect(within(card).getByRole('button', { name: 'Больше не нравится' })).toHaveTextContent('4'))
    expect(api.like).toHaveBeenCalledWith(1, 10, true)
    await userEvent.click(within(card).getByRole('button', { name: 'Больше не нравится' }))
    await waitFor(() => expect(api.like).toHaveBeenLastCalledWith(1, 10, false))
  })

  it('comments and replies', async () => {
    api.comments.mockResolvedValue([{
      id: 5, parent: null, status: 'visible', text: 'Круто!', created_at: new Date().toISOString(), mine: false,
      author: { type: 'student', student_id: 3, name: 'Чынара Ч', first_name: 'Чынара', group: { id: 2, name: 'PRO-02' }, photo: null }, replies: [],
    }])
    api.comment.mockResolvedValue({ id: 6, parent: 5, status: 'visible', text: 'Спасибо', created_at: '', mine: true, author: null })
    renderAt('/student/community')
    const card = (await screen.findAllByRole('article'))[1]
    await userEvent.click(within(card).getByRole('button', { name: /Комментарии/ }))
    expect(await within(card).findByText('Круто!')).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Ответить' }))
    expect(within(card).getByText('Ответ для Чынара')).toBeInTheDocument()
    await userEvent.type(within(card).getByRole('textbox', { name: 'Напиши комментарий…' }), 'Спасибо')
    await userEvent.click(within(card).getByRole('button', { name: 'Отправить' }))
    await waitFor(() => expect(api.comment).toHaveBeenCalledWith(1, 10, 'Спасибо', 5))
  })

  it('creates a post for review with category, photo and the policy shown', async () => {
    api.create.mockResolvedValue(post(20, { status: 'pending', mine: true }))
    renderAt('/student/community')
    await userEvent.click(await screen.findByRole('button', { name: /Чем хочешь поделиться, Айбек\?/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Новая публикация' })
    expect(within(dialog).getByText(/проверит преподаватель/)).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: /Новости/ })).not.toBeInTheDocument()   // staff only
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Текст публикации' }), 'Мой первый сайт!')
    await userEvent.click(within(dialog).getByRole('button', { name: /Отзыв/ }))
    await userEvent.click(within(dialog).getByRole('checkbox'))   // website consent appears for reviews only
    const file = new File(['x'], 'shot.png', { type: 'image/png' })
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview')
    globalThis.URL.revokeObjectURL = vi.fn()
    const input = dialog.querySelector('input[type=file]') as HTMLInputElement
    await userEvent.upload(input, file)
    expect(within(dialog).getByRole('button', { name: 'Убрать фото' })).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: /Отправить на проверку/ }))
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(1, expect.objectContaining({
      text: 'Мой первый сайт!', category: 'review', website_consent: true, submit: true, images: [file],
    })))
    expect(await screen.findByText('Отправлено на проверку — сообщим, когда опубликуют')).toBeInTheDocument()
  })

  it('shows the server reason when contact details are refused', async () => {
    api.create.mockRejectedValue({ response: { status: 400, data: { text: ['Без номеров телефонов — личные контакты в сообществе не публикуются.'] } } })
    renderAt('/student/community')
    await userEvent.click(await screen.findByRole('button', { name: /Чем хочешь поделиться/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Текст публикации' }), 'звони 0555 123 456')
    await userEvent.click(within(dialog).getByRole('button', { name: /Отправить на проверку/ }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Без номеров телефонов')
  })

  it('«Мои публикации» shows moderation status and the moderator note', async () => {
    api.mine.mockResolvedValue({ count: 1, next: null, previous: null, results: [post(30, {
      mine: true, can_edit: true, status: 'rejected', moderation: { note: 'Убери фамилию друга', moderated_at: null, submitted_at: null },
      author: { type: 'student', student_id: 1, name: 'Айбек Асанов', group: { id: 1, name: 'PRO-01' }, photo: null },
    })] })
    renderAt('/student/community')
    await userEvent.click(await screen.findByRole('tab', { name: /Мои публикации/ }))
    expect(await screen.findByText('Отклонено')).toBeInTheDocument()
    expect(screen.getByText(/Убери фамилию друга/)).toBeInTheDocument()
  })

  it('reports a post', async () => {
    api.reportPost.mockResolvedValue({} as never)
    renderAt('/student/community')
    const card = (await screen.findAllByRole('article'))[1]
    await userEvent.click(within(card).getByRole('button', { name: 'Действия' }))
    await userEvent.click(within(card).getByRole('menuitem', { name: /Пожаловаться/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Что не так?' })
    await userEvent.click(within(dialog).getByRole('radio', { name: 'Оскорбления или травля' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Отправить жалобу' }))
    await waitFor(() => expect(api.reportPost).toHaveBeenCalledWith(1, 10, 'bullying', ''))
    expect(await within(dialog).findByText('Спасибо! Модератор посмотрит.')).toBeInTheDocument()
  })

  it('notifications in Kyrgyz', async () => {
    window.localStorage.setItem('okk-student-portal-lang', 'ky')
    api.notifications.mockResolvedValue({ unread: 1, results: [{ id: 1, kind: 'reply', post_id: 10, comment_id: 6, actor: 'Бек', note: '', is_read: false, created_at: new Date().toISOString(), post_excerpt: 'Змейка' }] })
    api.readNotifications.mockResolvedValue({ unread: 0 })
    renderAt('/student/community')
    expect(await screen.findByRole('heading', { name: 'Коомчулук' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Билдирмелер/ }))
    expect(await screen.findByText('Бек комментарийиңе жооп берди')).toBeInTheDocument()
    await waitFor(() => expect(api.readNotifications).toHaveBeenCalledWith(1))
  })

  it('profile: badges, counts and projects only', async () => {
    api.profile.mockResolvedValue({
      id: 2, first_name: 'Бек', last_name: 'Бекова', name: 'Бек Бекова', group: { id: 1, name: 'PRO-01' }, photo: null,
      badges: [{ code: 'level', date: null, params: { level: 3 } }], posts_count: 4, likes_received: 12, projects: [post(10)], is_me: false,
    })
    renderAt('/student/community/u/2')
    expect(await screen.findByRole('heading', { name: 'Бек Бекова' })).toBeInTheDocument()
    expect(screen.getByText('Уровень 3')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(1)
  })
})

describe('Community moderation (staff)', () => {
  beforeEach(() => {
    mod.meta.mockResolvedValue({ pending: 1, open_reports: 0, can_announce_academy: true, can_send_to_website: true, groups: [{ id: 1, name: 'PRO-01' }] })
    mod.posts.mockResolvedValue({ count: 1, next: null, previous: null, results: [post(40, { status: 'pending', category: 'review', website_consent: true })] })
    mod.act.mockResolvedValue(post(40))
  })

  it('approves; rejecting needs a note for the student', async () => {
    renderWithProviders(<CommunityModerationPage />)
    expect(await screen.findByText('Сделала игру «Змейка» #40')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Отклонить' }))
    const reject = screen.getAllByRole('button', { name: 'Отклонить' }).at(-1)!
    expect(reject).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Что исправить (ученик увидит)'), 'Без фамилий друзей')
    await userEvent.click(reject)
    await waitFor(() => expect(mod.act).toHaveBeenCalledWith(40, 'reject', { note: 'Без фамилий друзей' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Одобрить' }))
    await waitFor(() => expect(mod.act).toHaveBeenCalledWith(40, 'approve', undefined))
  })
})
