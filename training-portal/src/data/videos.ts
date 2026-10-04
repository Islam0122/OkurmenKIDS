import type { Video } from '@/types'

/*
 * Useful videos — examples to be replaced by the administrator's own list
 * (later: from the Django API through contentService). Only URLs are kept;
 * no video file lives in the frontend.
 */
export const videos: Video[] = [
  {
    id: 'python-1h',
    title: 'Python for Beginners',
    description: 'Python тилинин негиздери бир саатта: өзгөрмөлөр, шарттар, циклдер.',
    url: 'https://www.youtube.com/watch?v=kqtD5dpn9C8',
    category: 'Python',
    duration: '1:00:00',
    order: 1,
    published: true,
  },
  {
    id: 'python-full',
    title: 'Learn Python — Full Course',
    description: 'Python боюнча толук курс: негиздерден долбоорлорго чейин.',
    url: 'https://www.youtube.com/watch?v=rfscVS0vtbw',
    category: 'Python',
    duration: '4:26:00',
    order: 2,
    published: true,
  },
  {
    id: 'html-css-full',
    title: 'HTML & CSS Full Course',
    description: 'HTML жана CSS: барактын структурасы, стилдер, Flexbox жана Grid.',
    url: 'https://www.youtube.com/watch?v=G3e-cpL7ofc',
    category: 'HTML / CSS',
    duration: '6:31:00',
    order: 3,
    published: true,
  },
]
