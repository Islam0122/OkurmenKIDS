import { useEffect, useState } from 'react'
import { ArrowRight, ArrowUpRight, Briefcase, ChevronDown, MapPin } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useCareersVacancies } from '@/hooks/useCareers'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/format'

import { FAQ, PERKS } from './content'
import { Eyebrow } from './Eyebrow'
import { formatSalary } from './format'
import { GlassesMark } from './Photo'
import { scrollToSection } from './scroll'
import { vacancyPath } from './VacancyCard'

/** Свежие опубликованные вакансии для витрины, плиток направлений и
 * быстрых ссылок (один запрос, кешируется React Query). */
export function useShowcase() {
  return useCareersVacancies({ ordering: 'newest', page: 1, page_size: 50 })
}

/** Первый экран без фотографии: живая витрина — реальные вакансии из API. */
export function HeroShowcase() {
  const list = useShowcase()
  const items = list.data?.results.slice(0, 3) ?? []
  const total = list.data?.count ?? 0
  return (
    <div className="relative">
      <div className="absolute -bottom-6 -left-6 hidden size-36 rounded-[28px] bg-ok-amber sm:block" aria-hidden />
      <div className="relative overflow-hidden rounded-[32px] rounded-tl-[96px] bg-ok-indigo p-6 text-white shadow-[0_40px_80px_-40px_rgba(23,14,69,0.6)] sm:p-9 sm:rounded-tl-[140px]">
        <div className="absolute -right-24 bottom-[-18%] w-[420px] opacity-15" aria-hidden><GlassesMark stroke="var(--color-ok-amber)" /></div>
        <div className="relative flex items-center justify-between gap-3 pl-14 sm:pl-24">
          <p className="flex items-center gap-2 text-[13px] font-bold uppercase tracking-[0.18em] text-ok-amber">
            <span className="relative flex size-2.5" aria-hidden>
              <span className="absolute inline-flex size-full rounded-full bg-ok-amber opacity-60 motion-safe:animate-ping" />
              <span className="relative inline-flex size-2.5 rounded-full bg-ok-amber" />
            </span>
            Сейчас ищем
          </p>
          {total ? <p className="text-sm font-semibold text-white/70">{total} {pluralize(total, 'вакансия', 'вакансии', 'вакансий')}</p> : null}
        </div>
        <div className="relative mt-8 space-y-3">
          {list.isPending ? (
            [0, 1, 2].map((i) => <div key={i} className="h-[92px] rounded-2xl bg-white/10 motion-safe:animate-pulse" />)
          ) : items.length ? (
            items.map((v, i) => {
              const salary = formatSalary(v.salary)
              return (
                <Link key={v.slug} to={vacancyPath(v.slug)}
                  className={cn('group flex items-center gap-4 rounded-2xl p-4 transition-colors sm:p-5',
                    i === 0 ? 'bg-white text-ok-ink hover:bg-ok-paper' : 'bg-white/10 text-white hover:bg-white/15')}>
                  <div className="min-w-0 flex-1">
                    <p className={cn('text-xs font-bold uppercase tracking-[0.14em]', i === 0 ? 'text-ok-indigo/70' : 'text-ok-amber')}>{v.department || v.employment_type_label}</p>
                    <p className="mt-1 line-clamp-2 text-lg font-extrabold leading-snug">{v.title}</p>
                    <p className={cn('mt-1 flex flex-wrap gap-x-3 text-sm', i === 0 ? 'text-ok-muted' : 'text-white/70')}>
                      {v.location ? <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden />{v.location}</span> : null}
                      <span className="inline-flex items-center gap-1"><Briefcase className="size-3.5" aria-hidden />{v.work_format_label}</span>
                      {salary ? <span className={cn('font-bold', i === 0 ? 'text-ok-indigo' : 'text-white')}>{salary}</span> : null}
                    </p>
                  </div>
                  <span className={cn('flex size-11 shrink-0 items-center justify-center rounded-full transition-transform motion-safe:group-hover:-translate-y-0.5 motion-safe:group-hover:translate-x-0.5',
                    i === 0 ? 'bg-ok-amber text-ok-indigo-deep' : 'bg-white/10 text-white')}>
                    <ArrowUpRight className="size-5" aria-hidden />
                  </span>
                </Link>
              )
            })
          ) : (
            <div className="rounded-2xl bg-white/10 p-6">
              <p className="text-xl font-extrabold">Открытых вакансий пока нет</p>
              <p className="mt-2 text-white/75">Новые вакансии появляются здесь сразу после публикации.</p>
            </div>
          )}
        </div>
        {total > items.length ? (
          <a href="#vacancies" onClick={(e) => { e.preventDefault(); scrollToSection('vacancies') }}
            className="relative mt-6 inline-flex items-center gap-2 text-[15px] font-bold text-ok-amber hover:underline">
            Все {total} {pluralize(total, 'вакансия', 'вакансии', 'вакансий')}<ArrowRight className="size-4" aria-hidden />
          </a>
        ) : null}
      </div>
    </div>
  )
}

/** Полоса «почему откликнуться через сайт» под первым экраном. */
export function PerksStrip() {
  return (
    <section aria-label="Как устроен отклик" className="border-y border-ok-line bg-white">
      <ul className="mx-auto grid max-w-7xl gap-px bg-ok-line sm:grid-cols-2 lg:grid-cols-4">
        {PERKS.map((p, i) => (
          <li key={p.title} className="bg-white px-5 py-7 sm:px-8">
            <p className="flex items-center gap-3 text-lg font-extrabold text-ok-indigo">
              <span className="flex size-8 items-center justify-center rounded-full bg-ok-amber-soft text-sm font-extrabold text-ok-amber-deep tabular-nums">{i + 1}</span>
              {p.title}
            </p>
            <p className="mt-2 text-[15px] leading-relaxed text-ok-muted">{p.text}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Частые вопросы кандидатов — нативные <details>, без скриптов и анимаций. */
export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="scroll-mt-20 bg-white">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-12 lg:py-28">
        <div className="lg:col-span-4">
          <Eyebrow>Вопросы и ответы</Eyebrow>
          <h2 id="faq-title" className="mt-5 text-3xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo sm:text-[2.6rem]">Частые вопросы кандидатов</h2>
          <p className="mt-5 text-lg leading-relaxed text-ok-muted">Если ответа нет — задайте вопрос HR на собеседовании или после отклика.</p>
        </div>
        <div className="divide-y divide-ok-line border-y border-ok-line lg:col-span-7 lg:col-start-6">
          {FAQ.map((item) => (
            <details key={item.q} className="group py-1">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-lg font-bold text-ok-ink marker:hidden [&::-webkit-details-marker]:hidden">
                {item.q}
                <ChevronDown className="size-5 shrink-0 text-ok-indigo transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <p className="max-w-2xl pb-6 text-[17px] leading-relaxed text-ok-muted">
                {item.a}{' '}
                {item.q.startsWith('Как вы обращаетесь') ? <Link to="/careers/privacy" className="font-semibold text-ok-indigo underline underline-offset-2">Подробнее</Link> : null}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

/** Быстрые ссылки на свежие вакансии в финальном призыве. */
export function QuickVacancyLinks() {
  const items = useShowcase().data?.results.slice(0, 3) ?? []
  if (!items.length) return null
  return (
    <ul className="mt-10 grid gap-2 sm:grid-cols-3" aria-label="Свежие вакансии">
      {items.map((v) => (
        <li key={v.slug} className="min-w-0">
          <Link to={vacancyPath(v.slug)} className="group flex h-full min-w-0 items-center justify-between gap-3 rounded-2xl bg-ok-indigo-deep/90 px-5 py-4 text-white transition-colors hover:bg-ok-indigo-deep">
            <span className="min-w-0">
              <span className="block truncate font-bold">{v.title}</span>
              <span className="block text-sm text-white/65">{v.work_format_label}</span>
            </span>
            <ArrowUpRight className="size-5 shrink-0 text-ok-amber" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Телефон: закреплённая кнопка к вакансиям, когда первый экран прокручен,
 * а сам раздел вакансий ещё не на экране. */
export function MobileCta() {
  const total = useShowcase().data?.count ?? 0
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const onScroll = () => {
      const vacancies = document.getElementById('vacancies')
      const contact = document.getElementById('contact')
      const past = window.scrollY > window.innerHeight * 0.8
      const inVacancies = vacancies ? vacancies.getBoundingClientRect().top < window.innerHeight && vacancies.getBoundingClientRect().bottom > 0 : false
      const inContact = contact ? contact.getBoundingClientRect().top < window.innerHeight : false
      setVisible(past && !inVacancies && !inContact)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  if (!total) return null
  return (
    <div className={cn('fixed inset-x-0 bottom-0 z-30 p-3 transition-transform duration-200 md:hidden', visible ? 'translate-y-0' : 'pointer-events-none translate-y-full')}
      style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }} aria-hidden={!visible}>
      <a href="#vacancies" tabIndex={visible ? 0 : -1} onClick={(e) => { e.preventDefault(); scrollToSection('vacancies') }}
        className="flex h-14 items-center justify-center gap-2 rounded-full bg-ok-indigo text-base font-bold text-white shadow-[0_16px_32px_-12px_rgba(23,14,69,0.6)]">
        Смотреть {total} {pluralize(total, 'вакансию', 'вакансии', 'вакансий')}<ArrowRight className="size-5" aria-hidden />
      </a>
    </div>
  )
}
