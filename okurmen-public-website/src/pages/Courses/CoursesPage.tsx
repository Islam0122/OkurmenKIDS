import { CourseCard } from '@/components/cards/CourseCard'
import { CardGrid } from '@/components/sections/CardGrid'
import { FinalCta } from '@/components/sections/FinalCta'
import { PageHero } from '@/components/shared/PageHero'
import { crumbsLd, Seo } from '@/components/shared/Seo'
import { CardSkeletons, EmptyState, ErrorState } from '@/components/shared/States'
import { useCourses } from '@/hooks/queries'
import { useI18n } from '@/i18n'
import { absoluteUrl } from '@/utils/media'

export function CoursesPage() {
  const { t, path, lang } = useI18n()
  const { data, isPending, isError, error, refetch } = useCourses()
  const courses = data?.results ?? []
  return (
    <>
      <Seo
        page="/courses"
        jsonLd={[
          crumbsLd(lang, 'courses'),
          {
            '@context': 'https://schema.org',
            '@type': 'ItemList',
            itemListElement: courses.map((c, i) => ({ '@type': 'ListItem', position: i + 1, url: absoluteUrl(path(`/courses/${c.slug}`)), name: c.title })),
          },
        ]}
      />
      <PageHero title={t('courses.title')} text={t('courses.subtitle')} crumbs={[{ label: t('nav.courses') }]} />
      <section className="container-page section">
        {isPending ? <CardSkeletons count={6} /> : isError ? <ErrorState error={error} onRetry={() => refetch()} /> : courses.length ? (
          <CardGrid items={courses} keyOf={(c) => c.slug} render={(c, i) => <CourseCard course={c} priority={i === 0} />} />
        ) : <EmptyState />}
      </section>
      <FinalCta />
    </>
  )
}
