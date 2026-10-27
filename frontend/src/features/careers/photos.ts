/** Фотографии карьерного сайта: файлы из `src/assets/careers/` (см. README
 * там же). Vite собирает их с хешем в имени; если файла нет, слот пустой и
 * страница показывает фирменную иллюстрацию (`Photo`), а не битую картинку. */

export type PhotoSlot = 'hero' | 'teaching' | 'team' | 'classroom' | 'culture'

const files = import.meta.glob<string>('../../assets/careers/*.{jpg,jpeg,png,webp,avif}', {
  eager: true,
  import: 'default',
  query: '?url',
})

function find(slot: PhotoSlot): string | null {
  const entry = Object.entries(files).find(([path]) => path.split('/').pop()?.replace(/\.[a-z]+$/, '') === slot)
  return entry ? entry[1] : null
}

export interface PhotoInfo {
  src: string | null
  alt: string
}

/** Подписи описывают сцену, а не конкретных людей: снимок может быть
 * иллюстративным, и выдавать его за сотрудников компании нельзя. */
const ALT: Record<PhotoSlot, string> = {
  hero: 'Занятие в OKURMEN KIDS: команда и ученики за работой',
  teaching: 'Тренер помогает ученикам на занятии',
  team: 'Команда обсуждает учебные планы',
  classroom: 'Учебный класс с рабочими местами учеников',
  culture: 'Команда на общем событии',
}

export function photo(slot: PhotoSlot): PhotoInfo {
  return { src: find(slot), alt: ALT[slot] }
}
