import { useEffect, type MouseEvent } from 'react'
import { ArrowDown, ArrowRight } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import { useCareersFilters } from '@/hooks/useCareers'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/format'

import { Eyebrow } from './Eyebrow'
import { ABOUT, COMPANY, HIRING_STEPS, REASONS, TEAMS } from './content'
import { Faq, HeroShowcase, MobileCta, PerksStrip, QuickVacancyLinks } from './Marketing'
import { GlassesMark, Photo } from './Photo'
import { photo } from './photos'
import { scrollToSection } from './scroll'
import { absoluteUrl, useDocumentMeta } from './useDocumentMeta'
import { VacanciesSection } from './VacanciesSection'

function anchor(id: string) {
  return (event: MouseEvent) => {
    event.preventDefault()
    window.history.replaceState(null, '', `#${id}`)
    scrollToSection(id)
  }
}

/** /careers — карьерный сайт OKURMEN KIDS. */
export function CareersHomePage() {
  const { hash } = useLocation()
  useDocumentMeta({
    title: `${COMPANY.siteName} — вакансии`,
    description: `${COMPANY.heroText} Актуальные вакансии и отклик без регистрации.`,
    url: absoluteUrl('/careers'),
  })
  useEffect(() => {
    if (!hash) return
    // Через два кадра: сначала закрывается мобильное меню (меняется высота
    // шапки), потом считаем позицию раздела — иначе прокрутка проскакивает.
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => scrollToSection(hash.slice(1)))
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [hash])

  return (
    <>
      <Hero />
      <PerksStrip />
      <About />
      <Culture />
      <People />
      <VacanciesSection />
      <Hiring />
      <Faq />
      <FinalCta />
      <MobileCta />
    </>
  )
}

function Hero() {
  const filters = useCareersFilters()
  const total = filters.data?.total
  return (
    <section aria-labelledby="hero-title" className="relative overflow-hidden">
      <div className="mx-auto grid max-w-7xl items-center gap-12 px-5 pb-16 pt-8 sm:px-8 lg:grid-cols-12 lg:gap-8 lg:pb-24 lg:pt-14">
        <div className="min-w-0 lg:col-span-6">
          <Eyebrow>{COMPANY.heroEyebrow}</Eyebrow>
          <h1 id="hero-title" className="mt-6 text-[2.6rem] font-extrabold leading-[1.04] tracking-[-0.03em] text-ok-indigo sm:text-6xl lg:text-[4.25rem]">
            {COMPANY.heroTitleStart}{' '}
            <span className="relative inline-block whitespace-nowrap">
              <span className="relative z-10">{COMPANY.heroTitleAccent}</span>
              <span className="absolute inset-x-[-0.06em] bottom-[-0.02em] z-0 h-[0.2em] rounded-full bg-ok-amber" aria-hidden />
            </span>{' '}
            {COMPANY.heroTitleEnd}
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-relaxed text-ok-muted sm:text-xl">{COMPANY.heroText}</p>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <a href="#vacancies" onClick={anchor('vacancies')}
              className="group inline-flex h-14 items-center justify-center gap-2 rounded-full bg-ok-indigo px-8 text-base font-bold text-white transition-colors hover:bg-ok-indigo-soft">
              Смотреть вакансии
              <ArrowDown className="size-5 transition-transform motion-safe:group-hover:translate-y-0.5" aria-hidden />
            </a>
            <a href="#team" onClick={anchor('team')}
              className="inline-flex h-14 items-center justify-center rounded-full border-2 border-ok-indigo/15 px-8 text-base font-bold text-ok-indigo transition-colors hover:border-ok-indigo/40 hover:bg-white">
              Познакомиться с командой
            </a>
          </div>
          <dl className="mt-10 flex flex-wrap gap-x-10 gap-y-4 border-t border-ok-line pt-6">
            <div>
              <dt className="text-sm text-ok-muted">Открыто сейчас</dt>
              <dd className="mt-0.5 text-lg font-bold text-ok-indigo" aria-live="polite">
                {typeof total === 'number' ? (total ? `${total} ${pluralize(total, 'вакансия', 'вакансии', 'вакансий')}` : 'Пока нет вакансий') : '…'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-ok-muted">Отклик</dt>
              <dd className="mt-0.5 text-lg font-bold text-ok-indigo">Без регистрации</dd>
            </div>
          </dl>
        </div>

        <div className="relative min-w-0 lg:col-span-6">
          {photo('hero').src ? <HeroPhotos /> : <HeroShowcase />}
        </div>
      </div>
    </section>
  )
}

/** Первый экран с фотографиями (когда в src/assets/careers есть hero.*). */
function HeroPhotos() {
  return (
    <>
          <div className="relative ml-auto w-full sm:w-[86%] lg:w-[82%]">
            <div className="absolute -bottom-6 -left-6 hidden size-40 rounded-[28px] bg-ok-amber sm:block" aria-hidden />
            <Photo slot="hero" priority sizes="(min-width: 1024px) 45vw, 90vw" tone="indigo" textAt="top"
              className="aspect-[4/3] rounded-[28px] rounded-tl-[96px] shadow-[0_30px_60px_-30px_rgba(23,14,69,0.45)] sm:aspect-[4/5] sm:rounded-tl-[140px]"
              fallback={<p className="max-w-[17rem] pt-10 text-[1.7rem] font-extrabold leading-tight sm:pt-14">Учим технологиям, языку и умению работать вместе</p>} />
            <ul className="absolute bottom-5 right-5 hidden max-w-[60%] flex-wrap justify-end gap-1.5 sm:flex" aria-label="Направления обучения">
              {ABOUT.directions.map((d) => (
                <li key={d.title} className="rounded-full bg-white/95 px-3 py-1.5 text-xs font-bold text-ok-indigo shadow-sm">{d.title}</li>
              ))}
            </ul>
          </div>
          <Photo slot="teaching" sizes="(min-width: 1024px) 22vw, 50vw" tone="amber" motif={false}
            className="relative -mt-20 ml-0 aspect-[4/3] w-[58%] rounded-3xl border-[6px] border-ok-paper shadow-[0_24px_48px_-24px_rgba(23,14,69,0.5)] sm:-mt-36 sm:w-[46%] lg:absolute lg:bottom-[-2.5rem] lg:left-0 lg:mt-0 lg:w-[44%]"
            fallback={(
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] opacity-70">Наша команда</p>
                <p className="mt-2 text-lg font-extrabold leading-snug">Тренеры, ассистенты и специалисты</p>
              </div>
            )} />
    </>
  )
}

function About() {
  return (
    <section id="about" aria-labelledby="about-title" className="scroll-mt-20 bg-white">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
        <div className="grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <Eyebrow>О нас</Eyebrow>
            <h2 id="about-title" className="mt-5 text-3xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo sm:text-[2.6rem]">{ABOUT.statement}</h2>
          </div>
          <div className="lg:col-span-6 lg:col-start-7">
            <p className="text-lg leading-relaxed text-ok-muted">{ABOUT.text}</p>
            <h3 className="mt-10 text-sm font-bold uppercase tracking-[0.16em] text-ok-ink">Направления обучения</h3>
            <dl className="mt-4 grid border-t border-ok-line sm:grid-cols-2">
              {ABOUT.directions.map((d, i) => (
                <div key={d.title} className={cn('border-b border-ok-line py-5', i % 2 === 0 ? 'sm:pr-6' : 'sm:border-l sm:pl-6')}>
                  <dt className="flex items-baseline gap-3 text-xl font-bold text-ok-indigo">
                    <span className="text-sm font-bold text-ok-amber-deep tabular-nums">0{i + 1}</span>{d.title}
                  </dt>
                  <dd className="mt-1 text-[15px] text-ok-muted">{d.text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
        <div className="mt-20 grid gap-8 md:grid-cols-3">
          {ABOUT.audience.map((a) => (
            <div key={a.title} className="border-t-[3px] border-ok-indigo pt-5">
              <h3 className="text-xl font-bold text-ok-indigo">{a.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-ok-muted">{a.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Culture() {
  return (
    <section id="culture" aria-labelledby="culture-title" className="relative scroll-mt-20 overflow-hidden bg-ok-indigo text-white">
      <div className="absolute -bottom-24 -left-24 w-[560px] opacity-[0.08]" aria-hidden><GlassesMark stroke="var(--color-ok-amber)" /></div>
      <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-12 lg:py-28">
        <div className="lg:col-span-4">
          <div className="lg:sticky lg:top-28">
            <Eyebrow inverse>Культура</Eyebrow>
            <h2 id="culture-title" className="mt-5 text-3xl font-extrabold leading-tight tracking-[-0.02em] sm:text-[2.6rem]">Почему стоит присоединиться к команде</h2>
            <p className="mt-5 text-lg leading-relaxed text-white/70">Не список льгот, а то, из чего на самом деле состоит работа в образовательной компании.</p>
          </div>
        </div>
        <ol className="lg:col-span-7 lg:col-start-6">
          {REASONS.map((r, i) => (
            <li key={r.title} className="grid grid-cols-[auto_1fr] gap-x-6 border-b border-white/12 py-8 first:pt-0 last:border-b-0">
              <span className="flex size-12 items-center justify-center rounded-full bg-ok-amber text-ok-indigo-deep">
                <r.icon className="size-5" aria-hidden />
              </span>
              <div>
                <p className="text-sm font-bold text-ok-amber tabular-nums">0{i + 1}</p>
                <h3 className="mt-1 text-xl font-bold sm:text-2xl">{r.title}</h3>
                <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-white/75 sm:text-base">{r.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

function People() {
  return (
    <section id="team" aria-labelledby="team-title" className="scroll-mt-20">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <Eyebrow>Люди и атмосфера</Eyebrow>
            <h2 id="team-title" className="mt-5 text-3xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo sm:text-[2.6rem]">Одна команда — много профессий</h2>
          </div>
          <p className="max-w-md text-lg leading-relaxed text-ok-muted">Занятия, группы и родители — общая забота всех, кто работает в академии.</p>
        </div>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-12 lg:gap-5">
          <Photo slot="team" sizes="(min-width: 1024px) 58vw, 100vw" tone="paper" motif={false}
            className="aspect-[3/2] rounded-[24px] sm:col-span-2 lg:col-span-7"
            fallback={<p className="max-w-xs text-2xl font-bold leading-snug">Тренеры, ассистенты и специалисты работают над одним делом</p>} />
          <Photo slot="classroom" sizes="(min-width: 1024px) 40vw, 50vw" tone="indigo"
            className="aspect-[4/5] rounded-[24px] rounded-tr-[96px] lg:col-span-5 lg:row-span-2 lg:aspect-auto"
            fallback={<p className="text-xl font-bold leading-snug">Занятия в группах — по расписанию и с тренером</p>} />
          <Photo slot="culture" sizes="(min-width: 1024px) 24vw, 50vw" tone="amber" motif={false}
            className="aspect-square rounded-[24px] lg:col-span-3"
            fallback={<p className="text-lg font-bold leading-snug">Делиться знаниями — внутри команды тоже</p>} />
          <div className="rounded-[24px] bg-white p-6 sm:col-span-2 sm:p-8 lg:col-span-4">
            <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-ok-ink">Кто работает в академии</h3>
            <ul className="mt-4 divide-y divide-ok-line">
              {TEAMS.map((t) => (
                <li key={t.title} className="py-3">
                  <p className="font-bold text-ok-indigo">{t.title}</p>
                  <p className="text-sm leading-relaxed text-ok-muted">{t.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

function Hiring() {
  return (
    <section id="hiring" aria-labelledby="hiring-title" className="scroll-mt-20 border-t border-ok-line">
      <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:py-28">
        <div className="max-w-2xl">
          <Eyebrow>Как проходит отбор</Eyebrow>
          <h2 id="hiring-title" className="mt-5 text-3xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo sm:text-[2.6rem]">От отклика до первого рабочего дня</h2>
        </div>
        <ol className="relative mt-14 grid gap-10 md:grid-cols-4 md:gap-6">
          <span className="absolute left-6 top-6 hidden h-[2px] w-[calc(75%+1.5rem)] bg-ok-line md:block" aria-hidden />
          {HIRING_STEPS.map((step, i) => (
            <li key={step.title} className="relative grid grid-cols-[auto_1fr] gap-x-5 md:block">
              <span className={cn('relative z-10 flex size-12 items-center justify-center rounded-full text-lg font-extrabold',
                i === 0 ? 'bg-ok-amber text-ok-indigo-deep' : 'border-2 border-ok-indigo bg-ok-paper text-ok-indigo')}>{i + 1}</span>
              <div className="md:mt-6">
                <h3 className="text-xl font-bold text-ok-indigo">{step.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ok-muted">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-12 max-w-2xl text-sm text-ok-muted">Этапы отбора конкретной вакансии указаны в её описании.</p>
      </div>
    </section>
  )
}

function FinalCta() {
  return (
    <section id="contact" aria-labelledby="cta-title" className="scroll-mt-20 px-5 pb-20 sm:px-8 lg:pb-28">
      <div className="relative mx-auto max-w-7xl overflow-hidden rounded-[32px] bg-ok-amber px-6 py-14 sm:px-12 lg:px-16 lg:py-20">
        <div className="absolute -right-16 bottom-[-20%] w-[460px] opacity-25 sm:w-[600px]" aria-hidden><GlassesMark stroke="var(--color-ok-indigo)" /></div>
        <div className="relative max-w-2xl">
          <h2 id="cta-title" className="text-3xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo-deep sm:text-5xl">Давайте создавать будущее вместе</h2>
          <p className="mt-5 text-lg leading-relaxed text-ok-indigo-deep/80">
            Выберите вакансию и отправьте отклик — это займёт несколько минут. Вопросы о работе можно задать HR: после отклика с вами свяжутся по указанным контактам.
          </p>
          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center">
            <a href="#vacancies" onClick={anchor('vacancies')}
              className="inline-flex h-14 items-center justify-center gap-2 rounded-full bg-ok-indigo-deep px-8 text-base font-bold text-white transition-colors hover:bg-ok-indigo">
              Выбрать вакансию
              <ArrowRight className="size-5" aria-hidden />
            </a>
            <Link to="/careers/privacy" className="text-[15px] font-semibold text-ok-indigo-deep underline decoration-ok-indigo-deep/30 underline-offset-4 hover:decoration-ok-indigo-deep">
              Как мы обрабатываем данные кандидатов
            </Link>
          </div>
        </div>
        <div className="relative"><QuickVacancyLinks /></div>
      </div>
    </section>
  )
}
