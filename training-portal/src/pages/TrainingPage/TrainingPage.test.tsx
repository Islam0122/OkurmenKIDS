import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { AppRoutes } from '@/App'
import { STORAGE_KEYS } from '@/services/storageService'

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>)
}

describe('training flow', () => {
  it('asks for a valid name, shows feedback, finishes and saves the result locally', async () => {
    const user = userEvent.setup()
    renderAt('/training/web-basics')

    const dialog = await screen.findByRole('dialog', { name: 'Атыңызды жазыңыз' })
    await user.type(within(dialog).getByLabelText('Атыңыз'), 'A')
    await user.click(within(dialog).getByRole('button', { name: 'Баштоо' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('кеминде 2')

    await user.clear(within(dialog).getByLabelText('Атыңыз'))
    await user.type(within(dialog).getByLabelText('Атыңыз'), 'Айбек')
    await user.click(within(dialog).getByRole('button', { name: 'Баштоо' }))

    expect((await screen.findAllByText('Суроо 1 / 8')).length).toBeGreaterThan(0)
    expect(window.localStorage.getItem(STORAGE_KEYS.studentName)).toBe('"Айбек"')

    // Q1 right answer → «Текшерүү» → feedback, answer locked.
    await user.click(screen.getByRole('radio', { name: /HyperText Markup Language/ }))
    await user.click(screen.getByRole('button', { name: 'Текшерүү' }))
    expect(screen.getByRole('status')).toHaveTextContent('Туура жооп!')
    expect(screen.getByRole('radio', { name: /HyperText Markup Language/ })).toBeDisabled()

    // Q2 wrong answer → correct one and the explanation are shown.
    await user.click(screen.getByRole('button', { name: 'Кийинки' }))
    await user.click(screen.getByRole('radio', { name: /<link>/ }))
    await user.click(screen.getByRole('button', { name: 'Текшерүү' }))
    expect(screen.getByRole('status')).toHaveTextContent('Туура эмес жооп')
    expect(screen.getByRole('status')).toHaveTextContent('<a>')

    // Navigation shows the checked answers as correct / incorrect.
    await user.click(screen.getByRole('button', { name: 'Кийинки' }))
    const nav = screen.getByRole('navigation', { name: 'Суроолор боюнча навигация' })
    expect(within(nav).getByRole('button', { name: /Суроо 1: Туура$/ })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /Суроо 2: Туура эмес/ })).toBeInTheDocument()

    // Finish from the last question.
    await user.click(within(nav).getByRole('button', { name: /Суроо 8/ }))
    await user.click(screen.getByRole('button', { name: 'Аяктоо' }))
    const confirm = await screen.findByRole('dialog', { name: 'Тренировканы аяктайсызбы?' })
    await user.click(within(confirm).getByRole('button', { name: 'Аяктоо' }))

    expect(await screen.findByText('Айбек')).toBeInTheDocument()
    expect(screen.getByText('1 / 8')).toBeInTheDocument()
    expect(screen.getByText('Көбүрөөк машыгуу керек')).toBeInTheDocument()
    expect(window.localStorage.getItem(STORAGE_KEYS.trainingProgress)).toBe('{}')
    const board = JSON.parse(window.localStorage.getItem(STORAGE_KEYS.leaderboard) ?? '[]')
    expect(board[0]).toMatchObject({ name: 'Айбек', percent: 13, testId: 'web-basics' })

    await user.click(screen.getByRole('button', { name: 'Жоопторду көрүү' }))
    expect(screen.getByRole('region', { name: 'Жоопторуңуз' })).toBeInTheDocument()
  })

  it('resumes an attempt after a reload', async () => {
    const user = userEvent.setup()
    const first = renderAt('/training/web-basics')
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Атыңыз'), 'Мээрим')
    await user.click(within(dialog).getByRole('button', { name: 'Баштоо' }))
    await user.click(await screen.findByRole('button', { name: 'Кийинки' }))
    first.unmount()

    renderAt('/training/web-basics')
    expect((await screen.findAllByText('Суроо 2 / 8')).length).toBeGreaterThan(0)
    expect(screen.getByText('Мурунку тренировкаңды улантып жатасың.')).toBeInTheDocument()
  })

  it('the exam button points to the configured LMS URL, not to training', async () => {
    renderAt('/')
    const links = await screen.findAllByRole('link', { name: /Экзаменге өтүү/ })
    expect(links[0]).toHaveAttribute('href', 'https://lms.okurmen.kg/student/exams/')
  })
})
