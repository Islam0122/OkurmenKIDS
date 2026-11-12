/**
 * Формы контента сайта описаны данными: одна запись — одно поле. Общий
 * редактор (ResourcePage) строит из них форму, список и фильтры, поэтому
 * новый тип контента — это новая схема, а не новая страница.
 */
export type FieldType = 'text' | 'textarea' | 'richtext' | 'number' | 'date' | 'datetime' | 'select' | 'boolean' | 'image' | 'lines' | 'url'

export interface FieldDef {
  name: string
  label: string
  type: FieldType
  required?: boolean
  hint?: string
  /** key in meta.choices, or a special source (lms courses / teachers) */
  choices?: string
  /** «Переводы» group: field_ky / field_en are generated automatically. */
  translatable?: boolean
  wide?: boolean
  /** Where the editor puts the field: the main column (texts) or the side
   * «Параметры» card. Default — texts in the main column, the rest aside. */
  side?: boolean
  /** Soft length limit shown as a counter. */
  max?: number
}

export interface ResourceDef {
  key: 'courses' | 'events' | 'achievements' | 'news' | 'team' | 'testimonials' | 'stats' | 'branches' | 'banners'
  title: string
  single: string
  description: string
  /** Has the draft → review → published → archived workflow. */
  workflow?: 'full' | 'news'
  gallery?: boolean
  /** Field shown as the row title / subtitle / image in the list. */
  titleField: string
  subtitle?: (row: Record<string, unknown>, label: (choices: string, value: unknown) => string) => string
  image?: string
  filters?: { name: string; choices: string; label: string }[]
  fields: FieldDef[]
  publicPath?: string
  /** Short text shown in lists and used as the SEO description fallback. */
  excerptField?: string
  /** Main date shown in the list. */
  dateField?: string
  /** Main category shown in the list. */
  categoryField?: string
  /** Has SEO title / description (all publishable content). */
  seo?: boolean
}

export const RESOURCES: Record<ResourceDef['key'], ResourceDef> = {
  courses: {
    key: 'courses',
    title: 'Курсы',
    single: 'Курс',
    description: 'Страницы курсов /courses. Количество занятий — из курса в LMS; цену и длительность сайт показывает, только если они заполнены.',
    workflow: 'full',
    titleField: 'title',
    image: 'cover',
    subtitle: (r) => [r.course_name, r.age_min && r.age_max ? `${r.age_min}–${r.age_max} лет` : null].filter(Boolean).join(' · '),
    publicPath: '/courses',
    excerptField: 'tagline',
    seo: true,
    fields: [
      { name: 'title', label: 'Название', type: 'text', required: true, translatable: true, max: 150 },
      { name: 'course', label: 'Курс в LMS', type: 'select', choices: 'lms:courses', hint: 'Связь с учебным курсом (количество занятий берётся оттуда).' },
      { name: 'tagline', label: 'Короткое описание', type: 'text', translatable: true, wide: true },
      { name: 'body', label: 'Описание', type: 'richtext', translatable: true, wide: true },
      { name: 'outcomes', label: 'Чему научится ребёнок', type: 'lines', hint: 'Один пункт — одна строка.', translatable: true, wide: true },
      { name: 'curriculum', label: 'Программа', type: 'lines', hint: 'Одна строка — один модуль: «Название: описание».', translatable: true, wide: true },
      { name: 'age_min', label: 'Возраст от', type: 'number' },
      { name: 'age_max', label: 'Возраст до', type: 'number' },
      { name: 'duration', label: 'Длительность', type: 'text', hint: 'Например: 9 месяцев', translatable: true },
      { name: 'schedule', label: 'Формат занятий', type: 'text', side: true, hint: '2 раза в неделю по 90 минут' },
      { name: 'price', label: 'Стоимость', type: 'text', side: true, hint: 'Пусто — не показывается.' },
      { name: 'icon', label: 'Иконка', type: 'select', choices: 'course_icon', required: true },
      { name: 'project_category', label: 'Примеры проектов', type: 'select', choices: 'project_category', hint: 'Опубликованные проекты студентов этой категории.' },
      { name: 'cover', label: 'Обложка', type: 'image', wide: true },
      { name: 'is_featured', label: 'Популярный (на главной)', type: 'boolean' },
      { name: 'order', label: 'Порядок', type: 'number' },
      { name: 'slug', label: 'Адрес (slug)', type: 'text', side: true, hint: 'Пусто — из названия.' },
    ],
  },
  events: {
    key: 'events',
    title: 'События',
    single: 'Событие',
    description: 'Мероприятия /events: даты, место, галерея, регистрация. Регистрации — в разделе «Заявки».',
    workflow: 'full',
    gallery: true,
    titleField: 'title',
    image: 'cover',
    subtitle: (r, label) => [label('event_category', r.category), r.starts_at ? new Date(String(r.starts_at)).toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }) : '', r.registrations_count ? `регистраций: ${r.registrations_count}` : ''].filter(Boolean).join(' · '),
    filters: [{ name: 'category', choices: 'event_category', label: 'Тип' }],
    publicPath: '/events',
    excerptField: 'excerpt',
    dateField: 'starts_at',
    categoryField: 'category',
    seo: true,
    fields: [
      { name: 'title', label: 'Название', type: 'text', required: true, translatable: true, max: 200 },
      { name: 'category', label: 'Категория', type: 'select', choices: 'event_category', required: true },
      { name: 'excerpt', label: 'Короткое описание', type: 'textarea', translatable: true, wide: true, max: 300 },
      { name: 'body', label: 'Описание', type: 'richtext', translatable: true, wide: true },
      { name: 'starts_at', label: 'Дата мероприятия: начало', type: 'datetime', required: true },
      { name: 'ends_at', label: 'Окончание', type: 'datetime' },
      { name: 'location', label: 'Место', type: 'text', side: true },
      { name: 'branch', label: 'Филиал', type: 'select', choices: 'branches' },
      { name: 'cover', label: 'Обложка', type: 'image', wide: true },
      { name: 'registration_enabled', label: 'Регистрация открыта', type: 'boolean' },
      { name: 'registration_limit', label: 'Мест (пусто — без ограничения)', type: 'number' },
      { name: 'registration_deadline', label: 'Регистрация до', type: 'datetime' },
      { name: 'is_featured', label: 'На главной', type: 'boolean' },
      { name: 'slug', label: 'Адрес (slug)', type: 'text', side: true, hint: 'Пусто — из названия.' },
    ],
  },
  achievements: {
    key: 'achievements',
    title: 'Достижения',
    single: 'Достижение',
    description: 'Победы, награды, сертификаты, партнёрства — /achievements. Фото и сертификаты — в галерее.',
    workflow: 'full',
    gallery: true,
    titleField: 'title',
    image: 'cover',
    subtitle: (r, label) => [label('achievement_category', r.category), r.date ? new Date(String(r.date)).toLocaleDateString('ru-RU') : ''].filter(Boolean).join(' · '),
    filters: [{ name: 'category', choices: 'achievement_category', label: 'Категория' }],
    publicPath: '/achievements',
    excerptField: 'excerpt',
    dateField: 'date',
    categoryField: 'category',
    seo: true,
    fields: [
      { name: 'title', label: 'Название', type: 'text', required: true, translatable: true, max: 200 },
      { name: 'category', label: 'Категория', type: 'select', choices: 'achievement_category', required: true },
      { name: 'date', label: 'Дата', type: 'date', required: true },
      { name: 'recipient', label: 'Студент или организация', type: 'text', side: true, hint: 'Имя ребёнка — только с согласия семьи («Алия С.»).' },
      { name: 'excerpt', label: 'Короткое описание', type: 'textarea', translatable: true, wide: true, max: 300 },
      { name: 'body', label: 'Описание', type: 'richtext', translatable: true, wide: true },
      { name: 'cover', label: 'Обложка', type: 'image', wide: true },
      { name: 'is_featured', label: 'На главной', type: 'boolean' },
      { name: 'slug', label: 'Адрес (slug)', type: 'text', side: true, hint: 'Пусто — из названия.' },
    ],
  },
  news: {
    key: 'news',
    title: 'Новости',
    single: 'Новость',
    description: 'Публичные новости /news (те же, что в Django admin). Черновик → опубликовать сейчас или с датой в будущем.',
    workflow: 'news',
    gallery: true,
    titleField: 'title',
    image: 'cover',
    subtitle: (r, label) => [label('news_category', r.category), r.published_at ? new Date(String(r.published_at)).toLocaleDateString('ru-RU') : ''].filter(Boolean).join(' · '),
    filters: [{ name: 'category', choices: 'news_category', label: 'Категория' }],
    publicPath: '/news',
    excerptField: 'excerpt',
    dateField: 'published_at',
    categoryField: 'category',
    seo: true,
    fields: [
      { name: 'title', label: 'Заголовок', type: 'text', required: true, wide: true, translatable: true, max: 200 },
      { name: 'category', label: 'Категория', type: 'select', choices: 'news_category', required: true },
      { name: 'excerpt', label: 'Краткое описание', type: 'textarea', wide: true, translatable: true, max: 300 },
      { name: 'body', label: 'Текст', type: 'richtext', wide: true, translatable: true, hint: 'Сайт OkurmenKids Digital в LMS показывает заголовки, списки и абзацы; новый сайт — всё оформление.' },
      { name: 'cover', label: 'Обложка', type: 'image', wide: true },
      { name: 'cover_caption', label: 'Подпись к обложке', type: 'text', side: true },
      { name: 'is_featured', label: 'Главная новость', type: 'boolean' },
      { name: 'show_author', label: 'Показывать автора', type: 'boolean' },
      { name: 'slug', label: 'Адрес (slug)', type: 'text', side: true, hint: 'Пусто — из заголовка.' },
    ],
  },
  team: {
    key: 'team',
    title: 'Команда',
    single: 'Сотрудник',
    description: 'Публичные профили /team. Тренер появляется на сайте только через профиль; фото — только с отметкой о согласии.',
    workflow: 'full',
    titleField: 'display_name',
    image: 'photo',
    subtitle: (r, label) => [r.position, label('team_group', r.group), r.photo_approved ? 'фото согласовано' : 'фото не согласовано'].filter(Boolean).join(' · '),
    filters: [{ name: 'group', choices: 'team_group', label: 'Отдел' }],
    excerptField: 'bio',
    categoryField: 'group',
    seo: true,
    fields: [
      { name: 'teacher', label: 'Тренер в LMS', type: 'select', choices: 'lms:teachers', hint: 'Имя, опыт и предметы подставятся из LMS, если не заполнены здесь.' },
      { name: 'name', label: 'Имя на сайте', type: 'text', hint: 'Пусто — имя тренера из LMS.' },
      { name: 'position', label: 'Должность', type: 'text', required: true, translatable: true },
      { name: 'group', label: 'Отдел на сайте', type: 'select', choices: 'team_group', hint: 'Раздел и фильтр на странице «Команда».' },
      { name: 'specialization', label: 'Специализация', type: 'text', side: true },
      { name: 'bio', label: 'О себе', type: 'textarea', translatable: true, wide: true },
      { name: 'career', label: 'Карьера', type: 'lines', translatable: true, wide: true, hint: 'Одна строка — одно место работы: «2022–н.в.: Тренер, Okurmen Kids».' },
      { name: 'achievements', label: 'Международные программы и достижения', type: 'lines', translatable: true, wide: true, hint: 'Одна строка — одна программа или награда. Только подтверждённые факты.' },
      { name: 'experience_years', label: 'Опыт (лет)', type: 'number', hint: 'Пусто — опыт на сайте не показывается.' },
      { name: 'photo', label: 'Фото для сайта', type: 'image', wide: true },
      { name: 'photo_approved', label: 'Фото согласовано для сайта', type: 'boolean' },
      { name: 'order', label: 'Порядок', type: 'number' },
      { name: 'slug', label: 'Адрес профиля (slug)', type: 'text', side: true, hint: '/team/<slug>. Пусто — из имени.' },
    ],
  },
  testimonials: {
    key: 'testimonials',
    title: 'Отзывы',
    single: 'Отзыв',
    description: 'Отзывы родителей и студентов /testimonials. Публикуются только с согласия автора.',
    workflow: 'full',
    titleField: 'author_name',
    image: 'photo',
    subtitle: (r, label) => [label('testimonial_role', r.author_role), r.rating ? `★ ${r.rating}` : '', r.video_url ? 'видео' : '', r.consent ? '' : 'нет согласия'].filter(Boolean).join(' · '),
    excerptField: 'text',
    categoryField: 'author_role',
    fields: [
      { name: 'author_name', label: 'Подпись автора', type: 'text', required: true, hint: '«Айгуль, мама Эмира» — как разрешил автор.' },
      { name: 'author_role', label: 'Кто', type: 'select', choices: 'testimonial_role', required: true },
      { name: 'course_label', label: 'Курс', type: 'text', side: true },
      { name: 'language', label: 'Язык отзыва', type: 'select', choices: 'language', required: true },
      { name: 'text', label: 'Отзыв', type: 'textarea', wide: true },
      { name: 'rating', label: 'Оценка (1–5)', type: 'number' },
      { name: 'video_url', label: 'Видео-отзыв (YouTube / Vimeo)', type: 'url', side: true },
      { name: 'photo', label: 'Фото', type: 'image', wide: true },
      { name: 'consent', label: 'Есть согласие автора на публикацию', type: 'boolean' },
      { name: 'is_featured', label: 'На главной', type: 'boolean' },
      { name: 'order', label: 'Порядок', type: 'number' },
    ],
  },
  stats: {
    key: 'stats',
    title: 'Показатели',
    single: 'Показатель',
    description: 'Цифры академии на главной и «Об академии». Только реальные данные.',
    titleField: 'value',
    subtitle: (r) => String(r.label ?? ''),
    fields: [
      { name: 'value', label: 'Значение', type: 'text', required: true, side: true, hint: '1200+, 8 лет, 95%' },
      { name: 'label', label: 'Подпись', type: 'text', required: true, translatable: true },
      { name: 'is_active', label: 'Показывать', type: 'boolean' },
      { name: 'order', label: 'Порядок', type: 'number' },
    ],
  },
  branches: {
    key: 'branches',
    title: 'Филиалы',
    single: 'Филиал',
    description: 'Адреса на странице «Контакты», в подвале и в форме записи.',
    titleField: 'name',
    subtitle: (r) => String(r.address ?? ''),
    fields: [
      { name: 'name', label: 'Название', type: 'text', required: true, translatable: true },
      { name: 'address', label: 'Адрес', type: 'text', required: true, translatable: true, wide: true },
      { name: 'phone', label: 'Телефон', type: 'text', side: true },
      { name: 'working_hours', label: 'Часы работы', type: 'text', side: true },
      { name: 'map_url', label: 'Ссылка на карту', type: 'url' },
      { name: 'latitude', label: 'Широта', type: 'number' },
      { name: 'longitude', label: 'Долгота', type: 'number' },
      { name: 'is_active', label: 'Показывать', type: 'boolean' },
      { name: 'order', label: 'Порядок', type: 'number' },
    ],
  },
  banners: {
    key: 'banners',
    title: 'Баннеры',
    single: 'Баннер',
    description: 'Баннеры на главной, в заданные даты.',
    titleField: 'title',
    image: 'image',
    subtitle: (r) => (r.is_active ? 'включён' : 'выключен'),
    fields: [
      { name: 'title', label: 'Заголовок', type: 'text', required: true, translatable: true },
      { name: 'text', label: 'Текст', type: 'text', translatable: true, wide: true },
      { name: 'image', label: 'Изображение', type: 'image' },
      { name: 'cta_label', label: 'Текст кнопки', type: 'text', side: true },
      { name: 'cta_url', label: 'Ссылка кнопки', type: 'text', side: true, hint: '/courses или https://…' },
      { name: 'starts_at', label: 'Показывать с', type: 'datetime' },
      { name: 'ends_at', label: 'Показывать до', type: 'datetime' },
      { name: 'is_active', label: 'Включён', type: 'boolean' },
      { name: 'order', label: 'Порядок', type: 'number' },
    ],
  },
}

export const STATE_LABEL: Record<string, string> = {
  draft: 'Черновик',
  review: 'На согласовании',
  scheduled: 'Запланировано',
  published: 'На сайте',
  archived: 'В архиве',
}

/** Content types edited on the full-page editor (/marketing/site/<key>). */
export const CONTENT_KEYS: ResourceDef['key'][] = ['news', 'events', 'achievements', 'testimonials', 'team', 'courses', 'banners', 'stats', 'branches']

export const LANGS = [
  { code: 'ru', label: 'RU', name: 'Русский' },
  { code: 'ky', label: 'KG', name: 'Кыргызча' },
  { code: 'en', label: 'EN', name: 'English' },
] as const
export type Lang = (typeof LANGS)[number]['code']

export const ISSUE_LABEL: Record<string, string> = {
  cover: 'нет обложки',
  excerpt: 'нет описания',
  ky: 'нет перевода KG',
  en: 'нет перевода EN',
  seo: 'нет SEO',
}
