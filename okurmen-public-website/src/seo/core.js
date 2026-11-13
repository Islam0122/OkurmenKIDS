/**
 * SEO core — the single source of the public brand, canonical host, page
 * titles and descriptions, hreflang rules, JSON-LD and sitemap XML.
 *
 * Plain JavaScript (types in core.d.ts) so the same code runs in four places:
 *   • the React app (src/components/shared/Seo.tsx and the pages),
 *   • the Vercel Routing Middleware (middleware.ts — crawlers, real 404s),
 *   • the live sitemap function (api/sitemap.ts),
 *   • the build scripts (scripts/*.mjs — static HTML heads, fallback sitemap).
 *
 * Public brand: «OKURMEN KIDS» only. Internal systems (LMS, CMS, backend apps)
 * keep their own names — nothing here touches them.
 */

/** The one canonical origin: HTTPS + www. Every canonical, hreflang, og:url and sitemap URL uses it. */
export const SITE_ORIGIN = 'https://www.okurmenkids.com'
export const BRAND = 'OKURMEN KIDS'
/** Other spellings people search for (schema.org alternateName). */
export const BRAND_ALT = ['Okurmen Kids', 'Окурмен Кидс', 'OkurmenKids']

export const LANGS = ['ru', 'ky', 'en']
export const DEFAULT_LANG = 'ru'
export const HTML_LANG = { ru: 'ru', ky: 'ky', en: 'en' }
export const OG_LOCALE = { ru: 'ru_RU', ky: 'ky_KG', en: 'en_US' }

const TITLE_MAX = 60
const DESCRIPTION_MAX = 160
const DESCRIPTION_MIN = 120

/** '/courses' → '/ky/courses' (Russian has no prefix). */
export function localized(lang, path) {
  const clean = path.startsWith('/') ? path : `/${path}`
  if (lang === DEFAULT_LANG) return clean
  return clean === '/' ? `/${lang}` : `/${lang}${clean}`
}

/** '/ky/courses/python' → { lang: 'ky', rest: '/courses/python' } */
export function splitLang(pathname) {
  const match = (pathname || '/').match(/^\/(ky|en)(\/.*)?$/)
  if (match) return { lang: match[1], rest: match[2] || '/' }
  return { lang: DEFAULT_LANG, rest: pathname || '/' }
}

/** One spelling per URL: lower case (all slugs are lower case), no trailing slash, no query. */
export function canonicalPath(path) {
  const bare = (path || '/').split(/[?#]/)[0].toLowerCase().replace(/\/{2,}/g, '/')
  return bare.length > 1 ? bare.replace(/\/+$/, '') : '/'
}

export const absolute = (site, path) => `${site.replace(/\/+$/, '')}${path.startsWith('/') ? '' : '/'}${path}`

// ---------------------------------------------------------------------------
// Static pages: unique title (≈50–60 chars) and description (≈140–160 chars)
// per page and language. Facts only from the academy's own published content.
// `name` is the breadcrumb / navigation label (same as nav.* in the i18n files).
// ---------------------------------------------------------------------------

export const STATIC_PATHS = ['/', '/about', '/courses', '/projects', '/achievements', '/news', '/events', '/team', '/testimonials', '/contacts']

export const PAGES = {
  ru: {
    '/': {
      name: 'Главная',
      title: 'OKURMEN KIDS — IT-академия и программирование для детей',
      description: 'IT-академия OKURMEN KIDS в Бишкеке для детей 9–15 лет: Python, веб-разработка, React, создание игр и реальные проекты. Запишите ребёнка на пробный урок.',
    },
    '/about': {
      name: 'Об академии',
      title: 'Об академии OKURMEN KIDS — IT-образование детей в Бишкеке',
      description: 'OKURMEN KIDS — академия в Бишкеке, где дети изучают программирование и английский, создают проекты и развиваются всесторонне. Наша миссия, ценности и подход.',
    },
    '/courses': {
      name: 'Курсы',
      title: 'IT-курсы для детей в Бишкеке: Python, веб — OKURMEN KIDS',
      description: 'Курсы программирования для детей и подростков в Бишкеке: веб-разработка, React, Python, ИИ и английский. Сравните программы и выберите курс по возрасту.',
    },
    '/projects': {
      name: 'Проекты',
      title: 'Проекты учеников: сайты и веб-приложения — OKURMEN KIDS',
      description: 'Сайты и веб-приложения на HTML, CSS, JavaScript и React, которые создали ученики IT-академии OKURMEN KIDS в Бишкеке. Реальные проекты детей и подростков.',
    },
    '/achievements': {
      name: 'Достижения',
      title: 'Достижения учеников IT-академии в Бишкеке — OKURMEN KIDS',
      description: 'Победы, выпуски групп, стипендии и награды учеников OKURMEN KIDS. Как дети и подростки в Бишкеке растут в программировании, учёбе и спорте вместе с академией.',
    },
    '/news': {
      name: 'Новости',
      title: 'Новости IT-академии для детей в Бишкеке — OKURMEN KIDS',
      description: 'Новости OKURMEN KIDS: наборы на курсы программирования для детей, успехи и стипендии учеников, экскурсии в IT-компании и жизнь IT-академии в Бишкеке.',
    },
    '/events': {
      name: 'События',
      title: 'Мероприятия для детей: уроки и хакатоны — OKURMEN KIDS',
      description: 'Открытые уроки, мастер-классы и хакатоны IT-академии OKURMEN KIDS в Бишкеке. Мероприятия по программированию для детей и подростков и запись онлайн.',
    },
    '/team': {
      name: 'Команда',
      title: 'Тренеры и команда IT-академии для детей — OKURMEN KIDS',
      description: 'Команда OKURMEN KIDS: руководители, IT-специалисты и тренеры, которые учат детей программированию в Бишкеке и помогают им создавать собственные проекты.',
    },
    '/testimonials': {
      name: 'Отзывы',
      title: 'Отзывы родителей и учеников об IT-курсах — OKURMEN KIDS',
      description: 'Настоящие отзывы учеников и родителей об IT-академии OKURMEN KIDS в Бишкеке: как проходят занятия по программированию и каких результатов достигают дети.',
    },
    '/contacts': {
      name: 'Контакты',
      title: 'Контакты и запись на пробный урок в Бишкеке — OKURMEN KIDS',
      description: 'Адрес, телефон и WhatsApp IT-академии OKURMEN KIDS в Бишкеке. Запишите ребёнка на пробное занятие по программированию — мы подберём курс по возрасту.',
    },
  },
  ky: {
    '/': {
      name: 'Башкы бет',
      title: 'OKURMEN KIDS — балдар үчүн IT-академия жана курстар',
      description: 'Бишкектеги OKURMEN KIDS IT-академиясы 9–15 жаштагы балдар үчүн: Python, веб-иштеп чыгуу, React, оюн түзүү жана реалдуу долбоорлор. Сыноо сабагына жазылыңыз.',
    },
    '/about': {
      name: 'Академия жөнүндө',
      title: 'OKURMEN KIDS академиясы жөнүндө — балдар үчүн IT билим',
      description: 'OKURMEN KIDS — Бишкектеги академия: балдар программалоону жана англис тилин үйрөнүп, өз долбоорлорун түзүшөт. Биздин миссия, баалуулуктар жана ыкма.',
    },
    '/courses': {
      name: 'Курстар',
      title: 'Бишкекте балдар үчүн IT курстары: Python, веб — OKURMEN KIDS',
      description: 'Балдар жана өспүрүмдөр үчүн программалоо курстары: веб-иштеп чыгуу, React, Python, жасалма интеллект жана англис тили. Куракка жараша курс тандаңыз.',
    },
    '/projects': {
      name: 'Долбоорлор',
      title: 'Окуучулардын долбоорлору: сайттар, тиркемелер — OKURMEN KIDS',
      description: 'OKURMEN KIDS IT-академиясынын окуучулары HTML, CSS, JavaScript жана React менен түзгөн сайттар жана веб-тиркемелер. Балдардын реалдуу долбоорлору.',
    },
    '/achievements': {
      name: 'Жетишкендиктер',
      title: 'Окуучулардын жетишкендиктери — OKURMEN KIDS IT-академиясы',
      description: 'OKURMEN KIDS окуучуларынын жеңиштери, топтордун бүтүрүүсү, стипендиялар жана сыйлыктар. Бишкектеги балдар программалоодо жана окууда кантип өсүшөт.',
    },
    '/news': {
      name: 'Жаңылыктар',
      title: 'Балдар үчүн IT-академиянын жаңылыктары — OKURMEN KIDS',
      description: 'OKURMEN KIDS жаңылыктары: балдар үчүн программалоо курстарына кабыл алуу, окуучулардын ийгиликтери, стипендиялар жана Бишкектеги академиянын турмушу.',
    },
    '/events': {
      name: 'Иш-чаралар',
      title: 'Балдар үчүн иш-чаралар: ачык сабактар — OKURMEN KIDS',
      description: 'OKURMEN KIDS IT-академиясынын ачык сабактары, мастер-класстары жана хакатондору. Бишкектеги балдар жана өспүрүмдөр үчүн программалоо боюнча иш-чаралар.',
    },
    '/team': {
      name: 'Команда',
      title: 'IT-академиянын тренерлери жана командасы — OKURMEN KIDS',
      description: 'OKURMEN KIDS командасы: Бишкекте балдарга программалоону үйрөткөн жана өз долбоорлорун түзүүгө жардам берген жетекчилер, IT-адистер жана тренерлер.',
    },
    '/testimonials': {
      name: 'Пикирлер',
      title: 'IT-курстар тууралуу ата-энелердин пикирлери — OKURMEN KIDS',
      description: 'OKURMEN KIDS IT-академиясы тууралуу окуучулардын жана ата-энелердин чыныгы пикирлери: программалоо сабактары кандай өтөт жана балдар кандай натыйжага жетет.',
    },
    '/contacts': {
      name: 'Байланыш',
      title: 'Байланыш жана сыноо сабагына жазылуу — OKURMEN KIDS',
      description: 'Бишкектеги OKURMEN KIDS IT-академиясынын дареги, телефону жана WhatsApp. Баланы программалоо боюнча сыноо сабагына жазыңыз — куракка жараша курс тандайбыз.',
    },
  },
  en: {
    '/': {
      name: 'Home',
      title: 'OKURMEN KIDS — Coding & IT Academy for Kids in Bishkek',
      description: 'OKURMEN KIDS is an IT academy in Bishkek for kids aged 9–15: Python, web development, React, game creation and real projects. Book a trial lesson now.',
    },
    '/about': {
      name: 'About',
      title: 'About OKURMEN KIDS — IT Education for Children in Bishkek',
      description: 'OKURMEN KIDS is an academy in Bishkek where children learn programming and English, build their own projects and grow as people. Our mission and values.',
    },
    '/courses': {
      name: 'Courses',
      title: 'Coding Courses for Kids in Bishkek: Python — OKURMEN KIDS',
      description: 'Programming courses for kids and teens in Bishkek: web development, React, Python, AI and English. Compare the programs and choose a course by age and level.',
    },
    '/projects': {
      name: 'Projects',
      title: 'Student Projects: Websites and Web Apps — OKURMEN KIDS',
      description: 'Websites and web apps built with HTML, CSS, JavaScript and React by students of the OKURMEN KIDS IT academy in Bishkek. Real projects made by kids and teens.',
    },
    '/achievements': {
      name: 'Achievements',
      title: 'Student Achievements at the IT Academy — OKURMEN KIDS',
      description: 'Wins, graduations, scholarships and awards of OKURMEN KIDS students. See how kids and teens in Bishkek grow in programming, studies and sport with the academy.',
    },
    '/news': {
      name: 'News',
      title: 'News from the IT Academy for Kids in Bishkek — OKURMEN KIDS',
      description: 'OKURMEN KIDS news: enrollment in coding courses for kids, student successes and scholarships, visits to IT companies and life at the academy in Bishkek.',
    },
    '/events': {
      name: 'Events',
      title: 'Events for Kids: Open Lessons and Hackathons — OKURMEN KIDS',
      description: 'Open lessons, workshops and hackathons at the OKURMEN KIDS IT academy in Bishkek. Programming events for kids and teens, with online registration.',
    },
    '/team': {
      name: 'Team',
      title: 'Trainers and Team of the IT Academy for Kids — OKURMEN KIDS',
      description: 'Meet the OKURMEN KIDS team: leaders, IT specialists and trainers who teach children programming in Bishkek and help them build their own projects.',
    },
    '/testimonials': {
      name: 'Testimonials',
      title: 'Parent and Student Reviews of Our IT Courses — OKURMEN KIDS',
      description: 'Real reviews from students and parents about the OKURMEN KIDS IT academy in Bishkek: what coding lessons are like and the results children achieve.',
    },
    '/contacts': {
      name: 'Contacts',
      title: 'Contacts and Trial Lesson Booking in Bishkek — OKURMEN KIDS',
      description: 'Address, phone and WhatsApp of the OKURMEN KIDS IT academy in Bishkek. Book a trial programming lesson for your child — we will help choose a course by age.',
    },
  },
}

export function pageSeo(lang, path) {
  return (PAGES[lang] ?? PAGES.ru)[path] ?? PAGES.ru[path] ?? null
}

// ---------------------------------------------------------------------------
// Detail pages (CMS content): title and description from the item itself.
// ---------------------------------------------------------------------------

/**
 * Sections with a page per item. `fields` are the translatable text fields:
 * the backend falls back to Russian for an untranslated field, so a language
 * whose fields are all identical to Russian is not a real translation.
 * `fields: null` = the content is Russian-only by design (no translation
 * fields in the backend): only the Russian URL is indexable.
 */
export const DETAIL = {
  courses: { api: (slug) => `/api/v1/public/site/courses/${slug}/`, fields: ['title', 'tagline', 'body'], name: (d) => d.title, text: (d) => d.tagline || d.body, image: (d) => d.cover?.url },
  events: { api: (slug) => `/api/v1/public/site/events/${slug}/`, fields: ['title', 'excerpt', 'body'], name: (d) => d.title, text: (d) => d.excerpt || d.body, image: (d) => d.cover?.url },
  achievements: { api: (slug) => `/api/v1/public/site/achievements/${slug}/`, fields: ['title', 'excerpt', 'body'], name: (d) => d.title, text: (d) => d.excerpt || d.body, image: (d) => d.cover?.url },
  team: { api: (slug) => `/api/v1/public/site/team/${slug}/`, fields: ['position', 'bio'], name: (d) => `${d.name} — ${d.position}`, text: (d) => d.bio || d.position, image: (d) => d.photo?.url },
  news: { api: (slug) => `/api/v1/public/news/${slug}/`, fields: null, name: (d) => d.title, text: (d) => d.excerpt || d.body, image: (d) => d.cover?.url },
  projects: { api: (slug) => `/api/v1/public/projects/${slug}/`, fields: null, name: (d) => d.title, subtitle: (d) => d.short_description, text: (d, lang) => projectText(d, lang), image: (d) => d.cover_url },
}

const TECH_LABEL = { ru: 'Технологии', ky: 'Технологиялар', en: 'Technologies' }

/** A student project's own text plus its real technology list («React HTML CSS» entries → «React, HTML, CSS»). */
export function projectText(project, lang = 'ru') {
  const seen = new Set()
  const techs = (project?.technologies ?? []).flatMap((entry) => String(entry).split(/[\s,]+/)).filter((tech) => tech && !seen.has(tech.toLowerCase()) && seen.add(tech.toLowerCase()))
  const own = plainText(project?.short_description || project?.description).replace(/[\s.!?]*$/, '')
  return [own, techs.length ? `${TECH_LABEL[lang] ?? TECH_LABEL.ru}: ${techs.join(', ')}` : ''].filter(Boolean).join('. ')
}

/** Language-specific part of a detail title — also what keeps the ru / ky / en titles of one item apart. */
const QUALIFIER = {
  ru: { courses: 'курс для детей в Бишкеке', events: 'мероприятие для детей', achievements: 'достижения учеников', team: 'команда академии', news: 'новости', projects: 'проект ученика' },
  ky: { courses: 'балдар үчүн курс', events: 'балдар үчүн иш-чара', achievements: 'жетишкендиктер', team: 'академиянын командасы', news: 'жаңылыктар', projects: 'окуучунун долбоору' },
  en: { courses: 'course for kids in Bishkek', events: 'event for kids', achievements: 'student achievements', team: 'academy team', news: 'news', projects: 'student project' },
}
/** Detail titles keep their language-specific part, so they may run a little over the 60 of static pages. */
const DETAIL_TITLE_MAX = 70

const SUFFIX = {
  ru: {
    courses: 'Курс IT-академии OKURMEN KIDS в Бишкеке. Запишите ребёнка на пробный урок.',
    events: 'Мероприятие IT-академии OKURMEN KIDS для детей и подростков в Бишкеке.',
    achievements: 'Достижения учеников IT-академии OKURMEN KIDS в Бишкеке.',
    team: 'Команда IT-академии для детей OKURMEN KIDS в Бишкеке.',
    news: 'Новости IT-академии для детей OKURMEN KIDS в Бишкеке.',
    projects: 'Проект ученика IT-академии OKURMEN KIDS в Бишкеке.',
  },
  ky: {
    courses: 'Бишкектеги OKURMEN KIDS IT-академиясынын курсу. Баланы сыноо сабагына жазыңыз.',
    events: 'OKURMEN KIDS IT-академиясынын балдар жана өспүрүмдөр үчүн иш-чарасы.',
    achievements: 'Бишкектеги OKURMEN KIDS IT-академиясынын окуучуларынын жетишкендиктери.',
    team: 'Бишкектеги балдар үчүн OKURMEN KIDS IT-академиясынын командасы.',
    news: 'Бишкектеги балдар үчүн OKURMEN KIDS IT-академиясынын жаңылыктары.',
    projects: 'Бишкектеги OKURMEN KIDS IT-академиясынын окуучусунун долбоору.',
  },
  en: {
    courses: 'A course at the OKURMEN KIDS IT academy in Bishkek. Book a trial lesson.',
    events: 'An OKURMEN KIDS IT academy event for kids and teens in Bishkek.',
    achievements: 'Achievements of OKURMEN KIDS IT academy students in Bishkek.',
    team: 'The team of the OKURMEN KIDS IT academy for kids in Bishkek.',
    news: 'News from the OKURMEN KIDS IT academy for kids in Bishkek.',
    projects: 'A student project from the OKURMEN KIDS IT academy in Bishkek.',
  },
}

/** Markup and emoji out, whitespace collapsed (titles and descriptions are plain text). */
export function plainText(value) {
  return String(value ?? '')
    .replace(/\p{Extended_Pictographic}|\uFE0F|\u200B|\u200D/gu, '')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[#>*_`~|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function clip(text, max) {
  if (text.length <= max) return text
  const cut = text.slice(0, max - 1)
  const space = cut.lastIndexOf(' ')
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,.;:—–-]+$/, '')}…`
}

/** Appends « — OKURMEN KIDS» unless the brand is already in the title. */
export function withBrand(title) {
  const clean = plainText(title)
  if (!clean) return BRAND
  return /okurmen\s*kids/i.test(clean) ? clean : `${clean} — ${BRAND}`
}

/**
 * «<name> — <section qualifier> | OKURMEN KIDS» (team: «<name — position> · <qualifier> | …»).
 * A long name is shortened, never the qualifier: an item with the same name
 * in two languages (people, «OKURMEN Kids Club — NEXT») still gets a
 * different title in each language.
 */
export function detailTitle(lang, section, name, seoTitle, subtitle) {
  if (seoTitle) return withBrand(seoTitle)
  const clean = plainText(name)
  // Student projects: «ShopVerce — Магазин электроники и техники» tells two projects with the same name apart.
  const described = subtitle ? `${clean} — ${plainText(subtitle).replace(/[\s.!?]*$/, '')} | ${BRAND}` : ''
  if (described && described.length <= DETAIL_TITLE_MAX && plainText(subtitle).toLowerCase() !== clean.toLowerCase()) return described
  const qualifier = (QUALIFIER[lang] ?? QUALIFIER.ru)[section]
  const brand = ` | ${BRAND}`
  if (!qualifier) return `${clip(clean, TITLE_MAX - brand.length)}${brand}`
  const joint = section === 'team' ? ' · ' : ' — '
  const tail = `${joint}${qualifier}${brand}`
  return `${clip(clean, DETAIL_TITLE_MAX - tail.length)}${tail}`
}

/** The item's own text (≤160 chars); a short one gets a factual sentence about the section. */
export function detailDescription(lang, section, text, seoDescription) {
  const own = plainText(seoDescription || text)
  const suffix = (SUFFIX[lang] ?? SUFFIX.ru)[section] ?? ''
  if (!own) return suffix
  if (own.length >= DESCRIPTION_MIN || seoDescription) return clip(own, DESCRIPTION_MAX)
  return clip(`${own.replace(/[\s.!?]*$/, '')}. ${suffix}`, DESCRIPTION_MAX)
}

/**
 * Languages in which an item really exists. `versions` = the API record per
 * language ({ ru, ky, en }; a missing language = not fetched / not found).
 */
export function translatedLangs(section, versions) {
  const spec = DETAIL[section]
  if (!versions.ru) return LANGS.filter((lang) => versions[lang])
  if (!spec?.fields) return ['ru']
  const signature = (record) => spec.fields.map((field) => String(record?.[field] ?? '').trim()).join('\u0001')
  const ru = signature(versions.ru)
  return LANGS.filter((lang) => lang === 'ru' || (versions[lang] && signature(versions[lang]) !== ru))
}

// ---------------------------------------------------------------------------
// JSON-LD (schema.org). Only real data from the CMS — no ratings, prices or
// addresses that the academy has not published.
// ---------------------------------------------------------------------------

const DAYS = { пн: 'Mo', вт: 'Tu', ср: 'We', чт: 'Th', пт: 'Fr', сб: 'Sa', вс: 'Su' }

/** «Пн–Вс, 10:00–20:00» → «Mo-Su 10:00-20:00» (schema.org openingHours); anything else → null. */
export function openingHours(text) {
  const match = String(text ?? '').toLowerCase().match(/^(пн|вт|ср|чт|пт|сб|вс)\s*[–—-]\s*(пн|вт|ср|чт|пт|сб|вс)[,\s]+(\d{1,2}:\d{2})\s*[–—-]\s*(\d{1,2}:\d{2})$/)
  return match ? `${DAYS[match[1]]}-${DAYS[match[2]]} ${match[3].padStart(5, '0')}-${match[4].padStart(5, '0')}` : null
}

const CITY = { ru: 'Бишкек', ky: 'Бишкек', en: 'Bishkek' }

/** The academy: Organization + EducationalOrganization (contacts and branches from the CMS settings). */
export function organizationLd(site, lang, settings) {
  const contacts = settings?.contacts ?? {}
  const branches = settings?.branches ?? []
  const story = plainText(String(settings?.about?.story ?? '').split(/\n\s*\n/)[0])
  const sameAs = [contacts.instagram, contacts.facebook, contacts.youtube, contacts.tiktok, contacts.telegram].filter((url) => typeof url === 'string' && /^https?:\/\//.test(url))
  const address = branches
    .filter((branch) => plainText(branch.address))
    .map((branch) => ({ '@type': 'PostalAddress', streetAddress: plainText(branch.address), addressLocality: CITY[lang] ?? CITY.ru, addressCountry: 'KG' }))
  const main = branches[0]
  const hours = main ? openingHours(plainText(main.working_hours)) : null
  return {
    '@context': 'https://schema.org',
    '@type': ['Organization', 'EducationalOrganization'],
    '@id': `${site}/#organization`,
    name: BRAND,
    alternateName: BRAND_ALT,
    url: `${site}/`,
    logo: { '@type': 'ImageObject', url: `${site}/logo.png`, width: 236, height: 213 },
    image: `${site}/og-image.png`,
    description: story || pageSeo(lang, '/').description,
    ...(contacts.phone ? { telephone: contacts.phone } : {}),
    ...(contacts.email ? { email: contacts.email } : {}),
    ...(sameAs.length ? { sameAs } : {}),
    ...(address.length ? { address: address.length === 1 ? address[0] : address } : { address: { '@type': 'PostalAddress', addressLocality: CITY[lang] ?? CITY.ru, addressCountry: 'KG' } }),
    ...(main?.latitude != null && main?.longitude != null ? { geo: { '@type': 'GeoCoordinates', latitude: main.latitude, longitude: main.longitude } } : {}),
    ...(main?.map_url ? { hasMap: main.map_url } : {}),
    ...(hours ? { openingHours: hours } : {}),
  }
}

export function websiteLd(site, lang) {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': `${site}/#website`,
    name: BRAND,
    alternateName: BRAND_ALT,
    url: `${site}/`,
    inLanguage: LANGS.map((code) => HTML_LANG[code]),
    description: pageSeo(lang, '/').description,
    publisher: { '@id': `${site}/#organization` },
  }
}

/** items: [{ name, path }] — paths already localized. */
export function breadcrumbLd(site, items) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({ '@type': 'ListItem', position: index + 1, name: plainText(item.name), item: absolute(site, item.path) })),
  }
}

/** Home › Section › Item, in the page's language. */
export function sectionCrumbs(lang, section, item) {
  const home = { name: pageSeo(lang, '/').name, path: localized(lang, '/') }
  const list = { name: pageSeo(lang, `/${section}`).name, path: localized(lang, `/${section}`) }
  return item ? [home, list, { name: item.name, path: localized(lang, `/${section}/${item.slug}`) }] : [home, list]
}

export const provider = (site) => ({ '@type': 'EducationalOrganization', '@id': `${site}/#organization`, name: BRAND, url: `${site}/` })

// ---------------------------------------------------------------------------
// Head tags as HTML (build-time static pages and the crawler middleware).
// ---------------------------------------------------------------------------

const escapeHtml = (value) => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
/** JSON inside <script>: no «</script>» break-out. */
const jsonForScript = (value) => JSON.stringify(value).replace(/</g, '\\u003c')

export const SEO_START = '<!--seo-->'
export const SEO_END = '<!--/seo-->'

/**
 * Every SEO tag of a page as an HTML string between <!--seo--> markers.
 * meta: { site, lang, path (unprefixed, e.g. '/courses/x'), title, description,
 *         image?, type?, langs? (indexable languages), noindex?, jsonLd?, publishedAt? }
 */
export function headTags(meta) {
  const { site, lang, path, title, description, image, type = 'website', noindex, jsonLd, publishedAt } = meta
  const langs = meta.langs?.length ? meta.langs : LANGS
  const ownLang = langs.includes(lang) ? lang : langs[0]
  const canonical = absolute(site, localized(ownLang, path))
  const ogImage = image ? (/^https?:/.test(image) ? image : absolute(site, image)) : `${site}/og-image.png`
  const tags = [
    `<title>${escapeHtml(title)}</title>`,
    `<meta name="description" content="${escapeHtml(description)}" />`,
    `<meta name="robots" content="${noindex ? 'noindex, follow' : 'index, follow, max-image-preview:large'}" />`,
    `<link rel="canonical" href="${escapeHtml(canonical)}" />`,
  ]
  if (!noindex && langs.length > 1 && langs.includes(lang)) {
    for (const code of langs) tags.push(`<link rel="alternate" hreflang="${code}" href="${escapeHtml(absolute(site, localized(code, path)))}" />`)
    tags.push(`<link rel="alternate" hreflang="x-default" href="${escapeHtml(absolute(site, localized(langs.includes('ru') ? 'ru' : langs[0], path)))}" />`)
  }
  tags.push(
    `<meta property="og:site_name" content="${BRAND}" />`,
    `<meta property="og:type" content="${type === 'article' ? 'article' : 'website'}" />`,
    `<meta property="og:title" content="${escapeHtml(title)}" />`,
    `<meta property="og:description" content="${escapeHtml(description)}" />`,
    `<meta property="og:url" content="${escapeHtml(canonical)}" />`,
    `<meta property="og:image" content="${escapeHtml(ogImage)}" />`,
    `<meta property="og:locale" content="${OG_LOCALE[lang] ?? OG_LOCALE.ru}" />`,
    ...(publishedAt ? [`<meta property="article:published_time" content="${escapeHtml(publishedAt)}" />`] : []),
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(description)}" />`,
    `<meta name="twitter:image" content="${escapeHtml(ogImage)}" />`,
  )
  const ld = [jsonLd].flat().filter(Boolean)
  if (ld.length) tags.push(`<script type="application/ld+json" data-seo-jsonld="true">${jsonForScript(ld.length === 1 ? ld[0] : ld)}</script>`)
  return `${SEO_START}\n    ${tags.join('\n    ')}\n    ${SEO_END}`
}

/** Puts the head tags (and optionally crawler-visible body text) into the built index.html. */
export function renderPage(template, meta, body) {
  let html = template.replace(/<html lang="[^"]*"/, `<html lang="${HTML_LANG[meta.lang] ?? 'ru'}"`)
  const block = headTags(meta)
  const start = html.indexOf(SEO_START)
  const end = html.indexOf(SEO_END)
  html = start >= 0 && end > start ? `${html.slice(0, start)}${block}${html.slice(end + SEO_END.length)}` : html.replace('</head>', `    ${block}\n  </head>`)
  if (body != null) html = html.replace(/<noscript>[\s\S]*?<\/noscript>/, `<noscript>${body}</noscript>`)
  return html
}

/** Crawler-visible text for a page (inside <noscript>): H1, description, section links. */
export function noscriptBody(lang, heading, description) {
  const links = STATIC_PATHS.map((path) => `<li><a href="${localized(lang, path)}">${escapeHtml(pageSeo(lang, path).name)}</a></li>`).join('')
  return `<h1>${escapeHtml(heading)}</h1><p>${escapeHtml(description)}</p><nav><ul>${links}</ul></nav>`
}

// ---------------------------------------------------------------------------
// Sitemap
// ---------------------------------------------------------------------------

/** Every indexable URL: static pages in all languages + published items in their real languages. */
export async function sitemapEntries(api, fetchJson) {
  const entries = STATIC_PATHS.map((path) => ({ path, langs: LANGS, lastmod: null, priority: path === '/' ? '1.0' : '0.8', changefreq: 'weekly' }))
  if (!api) return { entries, content: 0 }
  const feed = await fetchJson(`${api}/api/v1/public/site/sitemap/`)
  const PRIORITY = { courses: '0.9', news: '0.7', events: '0.7', projects: '0.6', achievements: '0.6', team: '0.5' }
  const jobs = []
  for (const section of Object.keys(PRIORITY)) {
    for (const item of feed?.[section] ?? []) {
      jobs.push((async () => {
        const spec = DETAIL[section]
        let langs = ['ru']
        if (spec.fields) {
          const versions = {}
          await Promise.all(LANGS.map(async (lang) => {
            versions[lang] = await fetchJson(`${api}${spec.api(item.slug)}?lang=${lang}`).catch(() => null)
          }))
          if (!versions.ru) return null
          langs = translatedLangs(section, versions)
        }
        return { path: `/${section}/${item.slug}`, langs, lastmod: item.updated_at?.slice(0, 10) ?? null, priority: PRIORITY[section], changefreq: 'monthly' }
      })())
    }
  }
  const content = (await Promise.all(jobs)).filter(Boolean)
  return { entries: [...entries, ...content], content: content.length }
}

const xmlEscape = (value) => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

export function sitemapXml(site, entries) {
  const urls = entries.flatMap((entry) =>
    entry.langs.map((lang) => {
      const alternates = entry.langs.length > 1
        ? [...entry.langs.map((code) => [code, localized(code, entry.path)]), ['x-default', localized(entry.langs.includes('ru') ? 'ru' : entry.langs[0], entry.path)]]
          .map(([code, path]) => `    <xhtml:link rel="alternate" hreflang="${code}" href="${xmlEscape(absolute(site, path))}"/>`)
        : []
      return [
        '  <url>',
        `    <loc>${xmlEscape(absolute(site, localized(lang, entry.path)))}</loc>`,
        entry.lastmod ? `    <lastmod>${entry.lastmod}</lastmod>` : null,
        `    <changefreq>${entry.changefreq}</changefreq>`,
        `    <priority>${entry.priority}</priority>`,
        ...alternates,
        '  </url>',
      ].filter(Boolean).join('\n')
    }),
  )
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n${urls.join('\n')}\n</urlset>\n`
}
