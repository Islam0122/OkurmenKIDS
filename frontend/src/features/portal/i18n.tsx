import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { BRAND } from '@/lib/brand'

import type { PortalAppId, PortalServiceId } from './config'

/**
 * OKURMENKIDS DIGITAL texts in Russian, Kyrgyz and English. Every visible string
 * of the portal lives here; components read them through `useI18n()`.
 */

export type Lang = 'ru' | 'kg' | 'en'

export const LANGS: { id: Lang; short: string; name: string; htmlLang: string }[] = [
  { id: 'ru', short: 'RU', name: 'Русский', htmlLang: 'ru' },
  { id: 'kg', short: 'KG', name: 'Кыргызча', htmlLang: 'ky' },
  { id: 'en', short: 'EN', name: 'English', htmlLang: 'en' },
]

export type ProgramId = 'it' | 'english' | 'soft-skills' | 'other'

interface AppText {
  name: string
  tagline: string
  features: string[]
}

interface ProgramText {
  name: string
  summary: string
  topics: string[]
}

interface Section {
  title: string
  text: string
}

export interface NewsText {
  title: string
  description: string
  featured: string
  readMore: string
  search: string
  searchLabel: string
  clearSearch: string
  filtersLabel: string
  categories: Record<'all' | 'events' | 'achievements' | 'competitions' | 'education' | 'announcements' | 'activities', string>
  latest: string
  found: (count: number) => string
  photos: (count: number) => string
  loadMore: string
  loading: string
  emptyTitle: string
  emptyText: string
  noResultsTitle: string
  noResultsText: string
  reset: string
  errorTitle: string
  errorText: string
  retry: string
  back: string
  notFoundTitle: string
  notFoundText: string
  author: string
  gallery: string
  share: string
  copyLink: string
  copied: string
  related: string
  photo: (index: number, total: number) => string
  open: (index: number) => string
  prev: string
  next: string
}

export interface GalleryText {
  title: string
  description: string
  search: string
  searchLabel: string
  clearSearch: string
  filtersLabel: string
  filters: Record<'all' | 'html-css' | 'javascript' | 'react' | 'python' | 'other', string>
  found: (count: number) => string
  view: string
  student: string
  group: string
  trainer: string
  date: string
  technologies: string
  hiddenStudent: string
  loadMore: string
  loading: string
  emptyTitle: string
  emptyText: string
  noResultsTitle: string
  noResultsText: string
  reset: string
  errorTitle: string
  errorText: string
  retry: string
  back: string
  notFoundTitle: string
  notFoundText: string
  demo: string
  about: string
  gallery: string
  noImages: string
  screenshot: (index: number, total: number) => string
  open: (index: number) => string
  prev: string
  next: string
}

export interface Messages {
  brand: { home: string }
  nav: { language: string; about: string; help: string; privacy: string; login: string; logout: string; time: string; checking: string; home: string }
  gallery: GalleryText
  news: NewsText
  hero: { tagline: string; hello: (name: string) => string; title: { before: string; accent: string; after: string }; description: string; appsLabel: string }
  card: { signIn: string; signInRequired: string; newTab: string; soon: string; explore: string }
  apps: Record<PortalAppId, AppText & { description?: string }>
  programs: Record<ProgramId, ProgramText>
  servicesTitle: string
  services: Record<PortalServiceId, { name: string; description: string }>
  programsPage: { back: string; title: string; titleAccent: string; subtitle: string; cta: string; ctaButton: string }
  footer: { links: string }
  modal: { close: string }
  about: {
    title: string
    description: string[]
    infoTitle: string
    info: { label: string; value: string }[]
    developerTitle: string
    developerRole: string
    technologies: string
    missionTitle: string
    mission: string
    footer: string[]
  }
  help: { title: string; subtitle: string; sections: Section[]; shortcut: string }
  privacy: { title: string; sections: Section[] }
}

const DEVELOPER = BRAND.developer

const en: Messages = {
  brand: { home: 'OkurmenKids Digital — home' },
  nav: { language: 'Language', about: 'About', help: 'Help', privacy: 'Privacy', login: 'Login', logout: 'Log out', time: 'Bishkek time', checking: 'Checking session', home: 'Home' },
  news: {
    title: 'Academy News',
    description: 'Stay updated with the latest news, events and achievements from Okurmen Kids Academy.',
    featured: 'Featured',
    readMore: 'Read More',
    search: 'Search news…',
    searchLabel: 'Search news',
    clearSearch: 'Clear search',
    filtersLabel: 'Filter by category',
    categories: { all: 'All News', events: 'Academy Events', achievements: 'Student Achievements', competitions: 'Competitions', education: 'Education', announcements: 'Announcements', activities: 'Activities' },
    latest: 'Latest news',
    found: (n) => `${n} ${n === 1 ? 'article' : 'articles'}`,
    photos: (n) => `${n} ${n === 1 ? 'photo' : 'photos'}`,
    loadMore: 'Show more news',
    loading: 'Loading news…',
    emptyTitle: 'No news yet',
    emptyText: 'Academy news will appear here as soon as it is published.',
    noResultsTitle: 'Nothing found',
    noResultsText: 'Try another search or category.',
    reset: 'Reset filters',
    errorTitle: 'Could not load news',
    errorText: 'Check your internet connection and try again.',
    retry: 'Try again',
    back: 'All news',
    notFoundTitle: 'Article not found',
    notFoundText: 'It may not be published yet, or the link is incorrect.',
    author: 'Author',
    gallery: 'Photo gallery',
    share: 'Share',
    copyLink: 'Copy link',
    copied: 'Link copied',
    related: 'Related news',
    photo: (i, n) => `Photo ${i} of ${n}`,
    open: (i) => `Enlarge photo ${i}`,
    prev: 'Previous',
    next: 'Next',
  },
  gallery: {
    title: 'Student Projects',
    description: 'Discover amazing projects created by students of Okurmen Kids Academy.',
    search: 'Project, technology, group…',
    searchLabel: 'Search projects',
    clearSearch: 'Clear search',
    filtersLabel: 'Filter by technology',
    filters: { all: 'All Projects', 'html-css': 'HTML/CSS', javascript: 'JavaScript', react: 'React', python: 'Python', other: 'Other' },
    found: (n) => `${n} ${n === 1 ? 'project' : 'projects'}`,
    view: 'View Project',
    student: 'Student',
    group: 'Group',
    trainer: 'Trainer',
    date: 'Project date',
    technologies: 'Technologies',
    hiddenStudent: 'Okurmen Kids student',
    loadMore: 'Show more projects',
    loading: 'Loading projects…',
    emptyTitle: 'No projects yet',
    emptyText: 'Projects appear here as soon as trainers publish them.',
    noResultsTitle: 'Nothing found',
    noResultsText: 'Try another search or technology.',
    reset: 'Reset filters',
    errorTitle: 'Could not load projects',
    errorText: 'Check your internet connection and try again.',
    retry: 'Try again',
    back: 'All projects',
    notFoundTitle: 'Project not found',
    notFoundText: 'It may have been unpublished, or the link is incorrect.',
    demo: 'Open live demo',
    about: 'About the project',
    gallery: 'Screenshots',
    noImages: 'No screenshots yet',
    screenshot: (i, n) => `Screenshot ${i} of ${n}`,
    open: (i) => `Open screenshot ${i}`,
    prev: 'Previous',
    next: 'Next',
  },
  hero: {
    tagline: 'Everything you need to learn, teach and grow.',
    hello: (name) => `Hello, ${name}`,
    title: { before: 'Welcome to OkurmenKids ', accent: 'Digital', after: '' },
    description: 'Your central platform for education, training, performance and academy resources.',
    appsLabel: 'Academy applications',
  },
  card: { signIn: 'Sign in', signInRequired: 'sign in required', newTab: 'opens in a new tab', soon: 'Soon', explore: 'Explore' },
  apps: {
    lms: { name: 'LMS', tagline: 'Learning Management System', features: ['Groups', 'Lessons', 'Homework', 'Attendance', 'Students'] },
    training: { name: 'Training & Exams', tagline: 'Practice, tests and exams', features: ['Practice', 'Tests', 'Exams', 'Exercises'] },
    schedule: { name: 'Schedule', tagline: 'Lessons and group timetables', features: ['Lessons', 'Groups', 'Trainers'] },
    leaderboard: { name: 'Leaderboard', tagline: 'Rankings, XP and achievements', features: ['Rankings', 'XP', 'Competitions'] },
    news: { name: 'News', tagline: 'Academy announcements and events', features: ['Updates', 'Events', 'Notices'] },
    performance: { name: 'Monthly Performance', tagline: 'Attendance and progress by month', features: ['Attendance', 'Homework', 'Progress'] },
    programs: {
      name: 'Our Programs',
      tagline: 'IT · English · Soft Skills',
      description: 'Explore our educational programs and discover your learning path.',
      features: ['IT', 'English', 'Soft Skills', 'Other Programs'],
    },
  },
  programs: {
    it: { name: 'IT', summary: 'Programming and digital skills — from the first lines of code to real projects.', topics: ['Programming', 'Computer literacy', 'Student projects'] },
    english: { name: 'English', summary: 'Spoken and written English for every level, built around practice.', topics: ['Speaking', 'Grammar', 'Vocabulary'] },
    'soft-skills': { name: 'Soft Skills', summary: 'Communication, teamwork and confidence that help in school and beyond.', topics: ['Communication', 'Teamwork', 'Public speaking'] },
    other: { name: 'Other Programs', summary: 'Additional academy courses, intensives and seasonal programs.', topics: ['Intensives', 'Seasonal courses', 'Events'] },
  },
  servicesTitle: 'More from Okurmen',
  services: {
    projects: { name: 'Student Projects', description: 'Portfolios and project gallery' },
    feedback: { name: 'Our Feedback', description: 'Student and trainer feedback' },
    website: { name: 'Our Website', description: 'Official academy website' },
    careers: { name: 'Our Careers', description: 'Vacancies for trainers and staff' },
  },
  programsPage: {
    back: 'All applications',
    title: 'Our',
    titleAccent: 'Programs',
    subtitle: 'Explore our educational programs and discover your learning path.',
    cta: 'Already studying? Practice and take tests in the training portal.',
    ctaButton: 'Training & Exams',
  },
  footer: { links: 'Footer' },
  modal: { close: 'Close' },
  about: {
    title: 'About OkurmenKids Digital',
    description: [
      'OkurmenKids Digital is a unified digital ecosystem developed to connect education, technology and student development.',
      'Our mission is to make education more accessible, organized and engaging by bringing all academy services into one platform.',
    ],
    infoTitle: 'Project Information',
    info: [
      { label: 'Project Name', value: 'OkurmenKids Digital' },
      { label: 'Created Date', value: '15.09.2026' },
      { label: 'Founder & Developer', value: DEVELOPER },
      { label: 'Organization', value: 'Okurmen Kids Academy' },
      { label: 'Category', value: 'Educational Technology' },
      { label: 'Platform', value: 'Web Application' },
      { label: 'Version', value: '1.0.0' },
    ],
    developerTitle: 'Created & Developed By',
    developerRole: 'Full-Stack Developer',
    technologies: 'Technologies',
    missionTitle: 'Our Mission',
    mission: 'Building a smarter educational environment where students can learn, practice, create projects and track their progress.',
    footer: [BRAND.copyright, BRAND.credit, 'Built with passion for education and technology.'],
  },
  help: {
    title: 'Help',
    subtitle: 'Getting around OkurmenKids Digital',
    sections: [
      { title: 'Opening applications', text: 'Click any card to open the application. Cards with ↗ open in a new tab, cards with → open here.' },
      { title: 'Logging in', text: 'Press Login and use the account the academy gave you. Cards with a lock (LMS, News) need a login — after signing in you return to the app you chose.' },
      { title: 'Navigating', text: 'Use Tab to move between cards and Enter to open one. Keys 1–7 open the cards directly. The logo always brings you back here.' },
      { title: 'Need more help?', text: 'Contact the academy administration or your trainer — they can restore access and answer questions about your account.' },
    ],
    shortcut: 'Esc closes this window',
  },
  privacy: {
    title: 'Privacy',
    sections: [
      { title: 'What this page stores', text: 'Only your language choice, saved in this browser. The launcher itself collects no personal data.' },
      { title: 'Signing in', text: 'Login uses your academy account. Each application handles its own data under the academy’s rules.' },
      { title: 'Questions', text: 'For questions about your data, contact the academy administration.' },
    ],
  },
}

const ru: Messages = {
  brand: { home: 'OkurmenKids Digital — на главную' },
  nav: { language: 'Язык', about: 'О проекте', help: 'Помощь', privacy: 'Конфиденциальность', login: 'Войти', logout: 'Выйти', time: 'Время в Бишкеке', checking: 'Проверяем сессию', home: 'На главную' },
  news: {
    title: 'Новости академии',
    description: 'Последние новости, события и достижения академии Okurmen Kids.',
    featured: 'Главное',
    readMore: 'Читать далее',
    search: 'Поиск новостей…',
    searchLabel: 'Поиск новостей',
    clearSearch: 'Очистить поиск',
    filtersLabel: 'Фильтр по категории',
    categories: { all: 'Все новости', events: 'Мероприятия академии', achievements: 'Достижения студентов', competitions: 'Соревнования', education: 'Обучение', announcements: 'Объявления', activities: 'Активности' },
    latest: 'Последние новости',
    found: (n) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'новость' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'новости' : 'новостей'}`,
    photos: (n) => `${n} фото`,
    loadMore: 'Показать ещё',
    loading: 'Загружаем новости…',
    emptyTitle: 'Новостей пока нет',
    emptyText: 'Новости академии появятся здесь сразу после публикации.',
    noResultsTitle: 'Ничего не найдено',
    noResultsText: 'Попробуйте другой запрос или категорию.',
    reset: 'Сбросить фильтры',
    errorTitle: 'Не удалось загрузить новости',
    errorText: 'Проверьте подключение к интернету и попробуйте ещё раз.',
    retry: 'Попробовать снова',
    back: 'Все новости',
    notFoundTitle: 'Новость не найдена',
    notFoundText: 'Возможно, она ещё не опубликована или ссылка неверна.',
    author: 'Автор',
    gallery: 'Фотогалерея',
    share: 'Поделиться',
    copyLink: 'Скопировать ссылку',
    copied: 'Ссылка скопирована',
    related: 'Читайте также',
    photo: (i, n) => `Фото ${i} из ${n}`,
    open: (i) => `Увеличить фото ${i}`,
    prev: 'Назад',
    next: 'Вперёд',
  },
  gallery: {
    title: 'Проекты студентов',
    description: 'Удивительные проекты, созданные студентами академии Okurmen Kids.',
    search: 'Проект, технология, группа…',
    searchLabel: 'Поиск проектов',
    clearSearch: 'Очистить поиск',
    filtersLabel: 'Фильтр по технологии',
    filters: { all: 'Все проекты', 'html-css': 'HTML/CSS', javascript: 'JavaScript', react: 'React', python: 'Python', other: 'Другое' },
    found: (n) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'проект' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'проекта' : 'проектов'}`,
    view: 'Смотреть проект',
    student: 'Студент',
    group: 'Группа',
    trainer: 'Тренер',
    date: 'Дата проекта',
    technologies: 'Технологии',
    hiddenStudent: 'Студент Okurmen Kids',
    loadMore: 'Показать ещё',
    loading: 'Загружаем проекты…',
    emptyTitle: 'Проектов пока нет',
    emptyText: 'Проекты появятся здесь, как только тренеры их опубликуют.',
    noResultsTitle: 'Ничего не найдено',
    noResultsText: 'Попробуйте другой запрос или технологию.',
    reset: 'Сбросить фильтры',
    errorTitle: 'Не удалось загрузить проекты',
    errorText: 'Проверьте подключение к интернету и попробуйте ещё раз.',
    retry: 'Попробовать снова',
    back: 'Все проекты',
    notFoundTitle: 'Проект не найден',
    notFoundText: 'Возможно, его сняли с публикации или ссылка неверна.',
    demo: 'Открыть демо',
    about: 'О проекте',
    gallery: 'Скриншоты',
    noImages: 'Скриншотов пока нет',
    screenshot: (i, n) => `Скриншот ${i} из ${n}`,
    open: (i) => `Открыть скриншот ${i}`,
    prev: 'Назад',
    next: 'Вперёд',
  },
  hero: {
    tagline: 'Всё, чтобы учиться, учить и расти.',
    hello: (name) => `Здравствуйте, ${name}`,
    title: { before: 'Добро пожаловать в OkurmenKids ', accent: 'Digital', after: '' },
    description: 'Единая платформа для обучения, тренировок, успеваемости и ресурсов академии.',
    appsLabel: 'Приложения академии',
  },
  card: { signIn: 'Вход', signInRequired: 'нужен вход', newTab: 'откроется в новой вкладке', soon: 'Скоро', explore: 'Смотреть' },
  apps: {
    lms: { name: 'LMS', tagline: 'Система управления обучением', features: ['Группы', 'Уроки', 'ДЗ', 'Посещаемость', 'Студенты'] },
    training: { name: 'Тренировки и экзамены', tagline: 'Практика, тесты и экзамены', features: ['Практика', 'Тесты', 'Экзамены', 'Упражнения'] },
    schedule: { name: 'Расписание', tagline: 'Уроки и расписание групп', features: ['Уроки', 'Группы', 'Тренеры'] },
    leaderboard: { name: 'Рейтинг', tagline: 'Рейтинги, XP и достижения', features: ['Рейтинги', 'XP', 'Соревнования'] },
    news: { name: 'Новости', tagline: 'Объявления и события академии', features: ['Обновления', 'События', 'Анонсы'] },
    performance: { name: 'Итоги месяца', tagline: 'Посещаемость и прогресс за месяц', features: ['Посещаемость', 'ДЗ', 'Прогресс'] },
    programs: {
      name: 'Наши программы',
      tagline: 'IT · English · Soft Skills',
      description: 'Изучите наши образовательные программы и найдите свой путь обучения.',
      features: ['IT', 'Английский', 'Soft Skills', 'Другие программы'],
    },
  },
  programs: {
    it: { name: 'IT', summary: 'Программирование и цифровые навыки — от первых строк кода до настоящих проектов.', topics: ['Программирование', 'Компьютерная грамотность', 'Проекты студентов'] },
    english: { name: 'Английский язык', summary: 'Устный и письменный английский для любого уровня, с упором на практику.', topics: ['Разговорная речь', 'Грамматика', 'Словарный запас'] },
    'soft-skills': { name: 'Soft Skills', summary: 'Общение, командная работа и уверенность — в учёбе и в жизни.', topics: ['Коммуникация', 'Командная работа', 'Публичные выступления'] },
    other: { name: 'Другие программы', summary: 'Дополнительные курсы академии, интенсивы и сезонные программы.', topics: ['Интенсивы', 'Сезонные курсы', 'Мероприятия'] },
  },
  servicesTitle: 'Больше от Okurmen',
  services: {
    projects: { name: 'Проекты студентов', description: 'Портфолио и галерея проектов' },
    feedback: { name: 'Обратная связь', description: 'Отзывы студентов и тренеров' },
    website: { name: 'Наш сайт', description: 'Официальный сайт академии' },
    careers: { name: 'Карьера', description: 'Вакансии тренеров и сотрудников' },
  },
  programsPage: {
    back: 'Все приложения',
    title: 'Наши',
    titleAccent: 'программы',
    subtitle: 'Изучите наши образовательные программы и найдите свой путь обучения.',
    cta: 'Уже учитесь? Тренируйтесь и проходите тесты на тренировочном портале.',
    ctaButton: 'Тренировки и экзамены',
  },
  footer: { links: 'Подвал' },
  modal: { close: 'Закрыть' },
  about: {
    title: 'Об OkurmenKids Digital',
    description: [
      'OkurmenKids Digital — единая цифровая экосистема, которая объединяет образование, технологии и развитие студентов.',
      'Наша миссия — сделать обучение доступнее, организованнее и интереснее, собрав все сервисы академии на одной платформе.',
    ],
    infoTitle: 'О проекте',
    info: [
      { label: 'Название проекта', value: 'OkurmenKids Digital' },
      { label: 'Дата создания', value: '15.09.2026' },
      { label: 'Основатель и разработчик', value: DEVELOPER },
      { label: 'Организация', value: 'Okurmen Kids Academy' },
      { label: 'Категория', value: 'Образовательные технологии' },
      { label: 'Платформа', value: 'Веб-приложение' },
      { label: 'Версия', value: '1.0.0' },
    ],
    developerTitle: 'Создано и разработано',
    developerRole: 'Full-Stack разработчик',
    technologies: 'Технологии',
    missionTitle: 'Наша миссия',
    mission: 'Создавать умную образовательную среду, где студенты учатся, практикуются, создают проекты и следят за своим прогрессом.',
    footer: [BRAND.copyright, BRAND.credit, 'Создано с любовью к образованию и технологиям.'],
  },
  help: {
    title: 'Помощь',
    subtitle: 'Как пользоваться OkurmenKids Digital',
    sections: [
      { title: 'Как открыть приложение', text: 'Нажмите на карточку. Карточки со стрелкой ↗ открываются в новой вкладке, со стрелкой → — здесь же.' },
      { title: 'Как войти', text: 'Нажмите «Войти» и используйте аккаунт, выданный академией. Карточкам с замком (LMS, Новости) нужен вход — после него вы вернётесь в выбранное приложение.' },
      { title: 'Навигация', text: 'Tab — переход между карточками, Enter — открыть. Клавиши 1–7 открывают карточки сразу. Логотип всегда возвращает сюда.' },
      { title: 'Нужна помощь?', text: 'Обратитесь в администрацию академии или к своему тренеру — они восстановят доступ и ответят на вопросы об аккаунте.' },
    ],
    shortcut: 'Esc закрывает это окно',
  },
  privacy: {
    title: 'Конфиденциальность',
    sections: [
      { title: 'Что хранит эта страница', text: 'Только выбранный язык — в этом браузере. Сам лаунчер не собирает персональные данные.' },
      { title: 'Вход', text: 'Вход выполняется через аккаунт академии. Каждое приложение работает со своими данными по правилам академии.' },
      { title: 'Вопросы', text: 'По вопросам о ваших данных обращайтесь в администрацию академии.' },
    ],
  },
}

const kg: Messages = {
  brand: { home: 'OkurmenKids Digital — башкы бет' },
  nav: { language: 'Тил', about: 'Долбоор жөнүндө', help: 'Жардам', privacy: 'Купуялык', login: 'Кирүү', logout: 'Чыгуу', time: 'Бишкек убактысы', checking: 'Сессия текшерилүүдө', home: 'Башкы бет' },
  news: {
    title: 'Академиянын жаңылыктары',
    description: 'Okurmen Kids академиясынын акыркы жаңылыктары, иш-чаралары жана жетишкендиктери.',
    featured: 'Башкы жаңылык',
    readMore: 'Толук окуу',
    search: 'Жаңылыктарды издөө…',
    searchLabel: 'Жаңылыктарды издөө',
    clearSearch: 'Издөөнү тазалоо',
    filtersLabel: 'Категория боюнча чыпкалоо',
    categories: { all: 'Бардык жаңылыктар', events: 'Академиянын иш-чаралары', achievements: 'Студенттердин жетишкендиктери', competitions: 'Мелдештер', education: 'Билим берүү', announcements: 'Кулактандыруулар', activities: 'Активдүүлүктөр' },
    latest: 'Акыркы жаңылыктар',
    found: (n) => `${n} жаңылык`,
    photos: (n) => `${n} сүрөт`,
    loadMore: 'Дагы көрсөтүү',
    loading: 'Жаңылыктар жүктөлүүдө…',
    emptyTitle: 'Азырынча жаңылыктар жок',
    emptyText: 'Академиянын жаңылыктары жарыялангандан кийин ушул жерде пайда болот.',
    noResultsTitle: 'Эч нерсе табылган жок',
    noResultsText: 'Башка суроо же категория менен аракет кылыңыз.',
    reset: 'Чыпкаларды тазалоо',
    errorTitle: 'Жаңылыктарды жүктөө мүмкүн болгон жок',
    errorText: 'Интернет байланышын текшерип, кайра аракет кылыңыз.',
    retry: 'Кайра аракет кылуу',
    back: 'Бардык жаңылыктар',
    notFoundTitle: 'Жаңылык табылган жок',
    notFoundText: 'Балким, ал али жарыялана элек же шилтеме туура эмес.',
    author: 'Автор',
    gallery: 'Сүрөт галереясы',
    share: 'Бөлүшүү',
    copyLink: 'Шилтемени көчүрүү',
    copied: 'Шилтеме көчүрүлдү',
    related: 'Дагы окуңуз',
    photo: (i, n) => `${n} сүрөттүн ${i}-си`,
    open: (i) => `${i}-сүрөттү чоңойтуу`,
    prev: 'Мурунку',
    next: 'Кийинки',
  },
  gallery: {
    title: 'Студенттердин долбоорлору',
    description: 'Okurmen Kids академиясынын студенттери түзгөн кызыктуу долбоорлор.',
    search: 'Долбоор, технология, топ…',
    searchLabel: 'Долбоорлорду издөө',
    clearSearch: 'Издөөнү тазалоо',
    filtersLabel: 'Технология боюнча чыпкалоо',
    filters: { all: 'Бардык долбоорлор', 'html-css': 'HTML/CSS', javascript: 'JavaScript', react: 'React', python: 'Python', other: 'Башка' },
    found: (n) => `${n} долбоор`,
    view: 'Долбоорду көрүү',
    student: 'Студент',
    group: 'Топ',
    trainer: 'Тренер',
    date: 'Долбоордун күнү',
    technologies: 'Технологиялар',
    hiddenStudent: 'Okurmen Kids студенти',
    loadMore: 'Дагы көрсөтүү',
    loading: 'Долбоорлор жүктөлүүдө…',
    emptyTitle: 'Азырынча долбоорлор жок',
    emptyText: 'Тренерлер жарыялаганда долбоорлор ушул жерде пайда болот.',
    noResultsTitle: 'Эч нерсе табылган жок',
    noResultsText: 'Башка суроо же технология менен аракет кылыңыз.',
    reset: 'Чыпкаларды тазалоо',
    errorTitle: 'Долбоорлорду жүктөө мүмкүн болгон жок',
    errorText: 'Интернет байланышын текшерип, кайра аракет кылыңыз.',
    retry: 'Кайра аракет кылуу',
    back: 'Бардык долбоорлор',
    notFoundTitle: 'Долбоор табылган жок',
    notFoundText: 'Балким, ал жарыялоодон алынган же шилтеме туура эмес.',
    demo: 'Демону ачуу',
    about: 'Долбоор жөнүндө',
    gallery: 'Скриншоттор',
    noImages: 'Азырынча скриншоттор жок',
    screenshot: (i, n) => `${n} скриншоттун ${i}-си`,
    open: (i) => `${i}-скриншотту ачуу`,
    prev: 'Мурунку',
    next: 'Кийинки',
  },
  hero: {
    tagline: 'Окуу, окутуу жана өсүү үчүн баары бир жерде.',
    hello: (name) => `Саламатсызбы, ${name}`,
    title: { before: 'OkurmenKids ', accent: 'Digital', after: '’га кош келиңиз' },
    description: 'Билим берүү, машыгуу, жетишкендиктер жана академиянын ресурстары үчүн борбордук платформа.',
    appsLabel: 'Академиянын тиркемелери',
  },
  card: { signIn: 'Кирүү', signInRequired: 'кирүү талап кылынат', newTab: 'жаңы өтмөктө ачылат', soon: 'Жакында', explore: 'Карап чыгуу' },
  apps: {
    lms: { name: 'LMS', tagline: 'Окутууну башкаруу системасы', features: ['Топтор', 'Сабактар', 'Үй тапшырма', 'Катышуу', 'Студенттер'] },
    training: { name: 'Машыгуу жана экзамендер', tagline: 'Практика, тесттер жана экзамендер', features: ['Практика', 'Тесттер', 'Экзамендер', 'Көнүгүүлөр'] },
    schedule: { name: 'Сабак жадыбалы', tagline: 'Сабактар жана топтордун жадыбалы', features: ['Сабактар', 'Топтор', 'Тренерлер'] },
    leaderboard: { name: 'Рейтинг', tagline: 'Рейтингдер, XP жана жетишкендиктер', features: ['Рейтингдер', 'XP', 'Мелдештер'] },
    news: { name: 'Жаңылыктар', tagline: 'Академиянын кулактандыруулары жана иш-чаралары', features: ['Жаңылануулар', 'Иш-чаралар', 'Билдирүүлөр'] },
    performance: { name: 'Айлык көрсөткүчтөр', tagline: 'Айлык катышуу жана прогресс', features: ['Катышуу', 'Үй тапшырма', 'Прогресс'] },
    programs: {
      name: 'Биздин программалар',
      tagline: 'IT · English · Soft Skills',
      description: 'Биздин билим берүү программалары менен таанышып, өз окуу жолуңузду табыңыз.',
      features: ['IT', 'Англис тили', 'Soft Skills', 'Башка программалар'],
    },
  },
  programs: {
    it: { name: 'IT', summary: 'Программалоо жана санариптик көндүмдөр — коддун алгачкы саптарынан чыныгы долбоорлорго чейин.', topics: ['Программалоо', 'Компьютердик сабаттуулук', 'Студенттердин долбоорлору'] },
    english: { name: 'Англис тили', summary: 'Ар бир деңгээл үчүн оозеки жана жазуу англис тили, практикага басым жасалат.', topics: ['Оозеки кеп', 'Грамматика', 'Сөз байлыгы'] },
    'soft-skills': { name: 'Soft Skills', summary: 'Окууда жана турмушта жардам берген баарлашуу, командада иштөө жана өзүнө ишеним.', topics: ['Баарлашуу', 'Командада иштөө', 'Эл алдында сүйлөө'] },
    other: { name: 'Башка программалар', summary: 'Академиянын кошумча курстары, интенсивдери жана сезондук программалары.', topics: ['Интенсивдер', 'Сезондук курстар', 'Иш-чаралар'] },
  },
  servicesTitle: 'Okurmen’дон дагы',
  services: {
    projects: { name: 'Долбоорлор', description: 'Портфолио жана долбоорлор галереясы' },
    feedback: { name: 'Пикирлер', description: 'Студенттердин жана тренерлердин пикири' },
    website: { name: 'Биздин сайт', description: 'Академиянын расмий сайты' },
    careers: { name: 'Карьера', description: 'Вакансиялар жана ишке алуу' },
  },
  programsPage: {
    back: 'Бардык тиркемелер',
    title: 'Биздин',
    titleAccent: 'программалар',
    subtitle: 'Биздин билим берүү программалары менен таанышып, өз окуу жолуңузду табыңыз.',
    cta: 'Окуп жатасызбы? Машыгуу порталында көнүгүп, тесттерди тапшырыңыз.',
    ctaButton: 'Машыгуу жана экзамендер',
  },
  footer: { links: 'Төмөнкү меню' },
  modal: { close: 'Жабуу' },
  about: {
    title: 'OkurmenKids Digital жөнүндө',
    description: [
      'OkurmenKids Digital — билим берүүнү, технологияны жана студенттердин өнүгүүсүн бириктирген бирдиктүү санариптик экосистема.',
      'Биздин миссия — академиянын бардык кызматтарын бир платформага чогултуп, билим алууну жеткиликтүү, иреттүү жана кызыктуу кылуу.',
    ],
    infoTitle: 'Долбоор тууралуу маалымат',
    info: [
      { label: 'Долбоордун аталышы', value: 'OkurmenKids Digital' },
      { label: 'Түзүлгөн күнү', value: '15.09.2026' },
      { label: 'Негиздөөчү жана иштеп чыгуучу', value: DEVELOPER },
      { label: 'Уюм', value: 'Okurmen Kids Academy' },
      { label: 'Категория', value: 'Билим берүү технологиялары' },
      { label: 'Платформа', value: 'Веб-тиркеме' },
      { label: 'Версия', value: '1.0.0' },
    ],
    developerTitle: 'Түзгөн жана иштеп чыккан',
    developerRole: 'Full-Stack иштеп чыгуучу',
    technologies: 'Технологиялар',
    missionTitle: 'Биздин миссия',
    mission: 'Студенттер окуп, көнүгүп, долбоор түзүп жана өз прогрессин көзөмөлдөй алган акылдуу билим берүү чөйрөсүн куруу.',
    footer: [BRAND.copyright, BRAND.credit, 'Билим берүүгө жана технологияга болгон сүйүү менен жасалган.'],
  },
  help: {
    title: 'Жардам',
    subtitle: 'OkurmenKids Digital’ды кантип колдонуу керек',
    sections: [
      { title: 'Тиркемени ачуу', text: 'Карточканы басыңыз. ↗ белгиси бар карточкалар жаңы өтмөктө, → белгиси барлар ушул жерде ачылат.' },
      { title: 'Кантип кирүү керек', text: '«Кирүү» баскычын басып, академия берген аккаунтту колдонуңуз. Кулпу белгиси бар карточкалар (LMS, Жаңылыктар) кирүүнү талап кылат — киргенден кийин тандалган тиркемеге кайтасыз.' },
      { title: 'Навигация', text: 'Tab — карточкалардын ортосунда өтүү, Enter — ачуу. 1–7 баскычтары карточкаларды дароо ачат. Логотип ар дайым бул жерге кайтарат.' },
      { title: 'Жардам керекпи?', text: 'Академиянын администрациясына же өз тренериңизге кайрылыңыз — алар кирүүнү калыбына келтирип, аккаунт боюнча суроолорго жооп беришет.' },
    ],
    shortcut: 'Esc бул терезени жабат',
  },
  privacy: {
    title: 'Купуялык',
    sections: [
      { title: 'Бул барак эмнени сактайт', text: 'Тандалган тилди гана — ушул браузерде. Лаунчер өзү жеке маалыматтарды чогултпайт.' },
      { title: 'Кирүү', text: 'Кирүү академиянын аккаунту аркылуу ишке ашат. Ар бир тиркеме өз маалыматтары менен академиянын эрежелери боюнча иштейт.' },
      { title: 'Суроолор', text: 'Маалыматтарыңыз боюнча суроолор болсо, академиянын администрациясына кайрылыңыз.' },
    ],
  },
}

export const MESSAGES: Record<Lang, Messages> = { ru, kg, en }

const STORAGE_KEY = 'okurmen-digital:lang'

function isLang(value: unknown): value is Lang {
  return value === 'ru' || value === 'kg' || value === 'en'
}

/** Saved choice → browser language → Russian (the academy's working language). */
export function detectLang(): Lang {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (isLang(saved)) return saved
  } catch {
    // storage blocked — fall through
  }
  const browser = (typeof navigator !== 'undefined' ? navigator.language : '').toLowerCase()
  if (browser.startsWith('ky')) return 'kg'
  if (browser.startsWith('en')) return 'en'
  return 'ru'
}

interface I18nValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: Messages
}

const I18nContext = createContext<I18nValue | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang)

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // storage blocked — the choice still applies to this visit
    }
  }, [])

  // Screen readers and hyphenation follow the chosen language.
  useEffect(() => {
    const root = document.documentElement
    const previous = root.lang
    root.lang = LANGS.find((item) => item.id === lang)?.htmlLang ?? 'ru'
    return () => {
      root.lang = previous
    }
  }, [lang])

  const value = useMemo(() => ({ lang, setLang, t: MESSAGES[lang] }), [lang, setLang])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used within a LanguageProvider')
  return ctx
}
