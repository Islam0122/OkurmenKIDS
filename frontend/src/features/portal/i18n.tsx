import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import type { PortalAppId } from './config'

/**
 * OKURMEN DIGITAL texts in Russian, Kyrgyz and English. Every visible string
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

export interface Messages {
  brand: { subtitle: string; home: string }
  nav: { language: string; about: string; help: string; privacy: string; login: string; logout: string; time: string; checking: string }
  hero: { tagline: string; hello: (name: string) => string; title: { before: string; accent: string; after: string }; description: string; appsLabel: string }
  card: { signIn: string; signInRequired: string; newTab: string; soon: string; explore: string }
  apps: Record<PortalAppId, AppText & { description?: string }>
  programs: Record<ProgramId, ProgramText>
  programsPage: { back: string; title: string; titleAccent: string; subtitle: string; cta: string; ctaButton: string }
  footer: { copyright: string; ecosystem: string; credit: string; links: string }
  modal: { close: string }
  about: {
    title: string
    subtitle: string
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

const DEVELOPER = 'Islam Duishobaev'

const en: Messages = {
  brand: { subtitle: 'Education Ecosystem', home: 'Okurmen Digital — home' },
  nav: { language: 'Language', about: 'About', help: 'Help', privacy: 'Privacy', login: 'Login', logout: 'Log out', time: 'Bishkek time', checking: 'Checking session' },
  hero: {
    tagline: 'Everything you need to learn, teach and grow.',
    hello: (name) => `Hello, ${name}`,
    title: { before: 'Welcome to Okurmen ', accent: 'Digital', after: '' },
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
  programsPage: {
    back: 'All applications',
    title: 'Our',
    titleAccent: 'Programs',
    subtitle: 'Explore our educational programs and discover your learning path.',
    cta: 'Already studying? Practice and take tests in the training portal.',
    ctaButton: 'Training & Exams',
  },
  footer: { copyright: '© 2026 Okurmen Digital', ecosystem: 'Education Ecosystem', credit: `Designed & Developed by ${DEVELOPER}.`, links: 'Footer' },
  modal: { close: 'Close' },
  about: {
    title: 'About Okurmen Digital',
    subtitle: 'Education Ecosystem',
    description: [
      'Okurmen Digital is a unified digital ecosystem developed to connect education, technology and student development.',
      'Our mission is to make education more accessible, organized and engaging by bringing all academy services into one platform.',
    ],
    infoTitle: 'Project Information',
    info: [
      { label: 'Project Name', value: 'Okurmen Digital' },
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
    footer: ['© 2026 Okurmen Digital. All rights reserved.', `Designed & Developed by ${DEVELOPER}.`, 'Built with passion for education and technology.'],
  },
  help: {
    title: 'Help',
    subtitle: 'Getting around Okurmen Digital',
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
  brand: { subtitle: 'Образовательная экосистема', home: 'Okurmen Digital — на главную' },
  nav: { language: 'Язык', about: 'О проекте', help: 'Помощь', privacy: 'Конфиденциальность', login: 'Войти', logout: 'Выйти', time: 'Время в Бишкеке', checking: 'Проверяем сессию' },
  hero: {
    tagline: 'Всё, чтобы учиться, учить и расти.',
    hello: (name) => `Здравствуйте, ${name}`,
    title: { before: 'Добро пожаловать в Okurmen ', accent: 'Digital', after: '' },
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
  programsPage: {
    back: 'Все приложения',
    title: 'Наши',
    titleAccent: 'программы',
    subtitle: 'Изучите наши образовательные программы и найдите свой путь обучения.',
    cta: 'Уже учитесь? Тренируйтесь и проходите тесты на тренировочном портале.',
    ctaButton: 'Тренировки и экзамены',
  },
  footer: { copyright: '© 2026 Okurmen Digital', ecosystem: 'Образовательная экосистема', credit: `Дизайн и разработка — ${DEVELOPER}.`, links: 'Подвал' },
  modal: { close: 'Закрыть' },
  about: {
    title: 'Об Okurmen Digital',
    subtitle: 'Образовательная экосистема',
    description: [
      'Okurmen Digital — единая цифровая экосистема, которая объединяет образование, технологии и развитие студентов.',
      'Наша миссия — сделать обучение доступнее, организованнее и интереснее, собрав все сервисы академии на одной платформе.',
    ],
    infoTitle: 'О проекте',
    info: [
      { label: 'Название проекта', value: 'Okurmen Digital' },
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
    footer: ['© 2026 Okurmen Digital. Все права защищены.', `Дизайн и разработка — ${DEVELOPER}.`, 'Создано с любовью к образованию и технологиям.'],
  },
  help: {
    title: 'Помощь',
    subtitle: 'Как пользоваться Okurmen Digital',
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
  brand: { subtitle: 'Билим берүү экосистемасы', home: 'Okurmen Digital — башкы бет' },
  nav: { language: 'Тил', about: 'Долбоор жөнүндө', help: 'Жардам', privacy: 'Купуялык', login: 'Кирүү', logout: 'Чыгуу', time: 'Бишкек убактысы', checking: 'Сессия текшерилүүдө' },
  hero: {
    tagline: 'Окуу, окутуу жана өсүү үчүн баары бир жерде.',
    hello: (name) => `Саламатсызбы, ${name}`,
    title: { before: 'Okurmen ', accent: 'Digital', after: '’га кош келиңиз' },
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
  programsPage: {
    back: 'Бардык тиркемелер',
    title: 'Биздин',
    titleAccent: 'программалар',
    subtitle: 'Биздин билим берүү программалары менен таанышып, өз окуу жолуңузду табыңыз.',
    cta: 'Окуп жатасызбы? Машыгуу порталында көнүгүп, тесттерди тапшырыңыз.',
    ctaButton: 'Машыгуу жана экзамендер',
  },
  footer: { copyright: '© 2026 Okurmen Digital', ecosystem: 'Билим берүү экосистемасы', credit: `Дизайн жана иштеп чыгуу — ${DEVELOPER}.`, links: 'Төмөнкү меню' },
  modal: { close: 'Жабуу' },
  about: {
    title: 'Okurmen Digital жөнүндө',
    subtitle: 'Билим берүү экосистемасы',
    description: [
      'Okurmen Digital — билим берүүнү, технологияны жана студенттердин өнүгүүсүн бириктирген бирдиктүү санариптик экосистема.',
      'Биздин миссия — академиянын бардык кызматтарын бир платформага чогултуп, билим алууну жеткиликтүү, иреттүү жана кызыктуу кылуу.',
    ],
    infoTitle: 'Долбоор тууралуу маалымат',
    info: [
      { label: 'Долбоордун аталышы', value: 'Okurmen Digital' },
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
    footer: ['© 2026 Okurmen Digital. Бардык укуктар корголгон.', `Дизайн жана иштеп чыгуу — ${DEVELOPER}.`, 'Билим берүүгө жана технологияга болгон сүйүү менен жасалган.'],
  },
  help: {
    title: 'Жардам',
    subtitle: 'Okurmen Digital’ды кантип колдонуу керек',
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
