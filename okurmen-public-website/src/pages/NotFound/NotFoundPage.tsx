import { Seo } from '@/components/shared/Seo'
import { NotFoundState } from '@/components/shared/States'
import { useI18n } from '@/i18n'

export function NotFoundPage() {
  const { t } = useI18n()
  return (
    <>
      <Seo title={t('state.notFound.title')} noindex />
      <NotFoundState />
    </>
  )
}
