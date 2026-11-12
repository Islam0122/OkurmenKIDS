import {
  Award, BookOpen, CalendarDays, FileStack, FolderKanban, Globe2, Home, Image, ImagePlay, Images, Inbox, KanbanSquare, Languages,
  LayoutDashboard, Megaphone, MessageSquareQuote, Newspaper, Phone, Search, Settings2, Share2, Tags, Users, type LucideIcon,
} from 'lucide-react'

export interface CmsNavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  /** Shown indented under the previous item (a part of that section). */
  child?: boolean
  /** Counter key from the overview (new leads…). */
  badge?: 'leads_new'
}

export interface CmsNavGroup {
  key: string
  label: string
  items: CmsNavItem[]
  /** Only editors (marketing, director, admin) — sales see leads only. */
  editorsOnly?: boolean
}

const B = '/marketing/site'

/** Информационная архитектура «Управление сайтом»: один пункт — одно место
 * редактирования. Главная и «Об академии» — внутри «Страниц сайта». */
export const CMS_NAV: CmsNavGroup[] = [
  { key: 'overview', label: '', editorsOnly: true, items: [{ to: B, label: 'Обзор сайта', icon: LayoutDashboard, end: true }] },
  {
    key: 'content',
    label: 'Контент',
    editorsOnly: true,
    items: [
      { to: `${B}/pages`, label: 'Страницы сайта', icon: FileStack, end: true },
      { to: `${B}/pages/home`, label: 'Главная страница', icon: Home, child: true },
      { to: `${B}/news`, label: 'Новости', icon: Newspaper },
      { to: `${B}/events`, label: 'События', icon: CalendarDays },
      { to: `${B}/achievements`, label: 'Достижения', icon: Award },
      { to: `${B}/projects`, label: 'Проекты учеников', icon: FolderKanban },
      { to: `${B}/testimonials`, label: 'Отзывы', icon: MessageSquareQuote },
      { to: `${B}/team`, label: 'Команда', icon: Users },
      { to: `${B}/courses`, label: 'Курсы', icon: BookOpen },
    ],
  },
  {
    key: 'media',
    label: 'Медиа',
    editorsOnly: true,
    items: [
      { to: `${B}/media`, label: 'Медиатека', icon: Images, end: true },
      { to: `${B}/media/images`, label: 'Изображения', icon: Image },
      { to: `${B}/media/videos`, label: 'Видео', icon: ImagePlay },
      { to: `${B}/banners`, label: 'Баннеры', icon: Megaphone },
    ],
  },
  {
    key: 'feedback',
    label: 'Обратная связь',
    items: [
      { to: `${B}/leads`, label: 'Заявки с сайта', icon: Inbox, end: true, badge: 'leads_new' },
      { to: `${B}/leads/board`, label: 'Статусы заявок', icon: KanbanSquare },
      { to: `${B}/contacts`, label: 'Контактная информация', icon: Phone },
    ],
  },
  {
    key: 'settings',
    label: 'Настройки',
    editorsOnly: true,
    items: [
      { to: `${B}/settings/seo`, label: 'SEO', icon: Search },
      { to: `${B}/settings/metadata`, label: 'Метаданные', icon: Tags },
      { to: `${B}/settings/social`, label: 'Социальные ссылки', icon: Share2 },
      { to: `${B}/settings/languages`, label: 'Языки сайта', icon: Languages },
      { to: `${B}/settings/general`, label: 'Общие настройки', icon: Settings2 },
    ],
  },
]

/** Sales see only the lead inbox (contacts are site settings — editors only). */
export function navFor(isEditor: boolean): CmsNavGroup[] {
  if (isEditor) return CMS_NAV
  return CMS_NAV.filter((g) => g.key === 'feedback').map((g) => ({ ...g, items: g.items.filter((i) => !i.to.endsWith('/contacts')) }))
}

/** Phone bottom bar: the four most used places + «Меню» (the full navigation). */
export const CMS_MOBILE: CmsNavItem[] = [
  { to: B, label: 'Обзор', icon: LayoutDashboard, end: true },
  { to: `${B}/pages`, label: 'Контент', icon: FileStack },
  { to: `${B}/media`, label: 'Медиа', icon: Images },
  { to: `${B}/leads`, label: 'Заявки', icon: Inbox, badge: 'leads_new' },
]

export const SITE_ICON = Globe2
