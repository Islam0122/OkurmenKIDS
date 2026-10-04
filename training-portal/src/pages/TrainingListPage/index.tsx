import { getTests } from '@/api/tests'
import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { CategorySections } from '@/components/CategorySections'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'

export function TrainingListPage() {
  const { data, loading, error, reload } = useAsync(getTests)
  return (
    <div className="training-page">
      <header className="training-page__head">
        <h1 className="page-title">{t.home.testsTitle}</h1>
        <p className="section-subtitle">{t.home.testsSubtitle}</p>
      </header>
      {loading ? <Loader /> : error ? <ErrorState error={error} onRetry={reload} /> : data?.length ? (
        <CategorySections tests={data} filter />
      ) : (
        <div className="empty"><Icon name="clipboard" /><p>{t.home.noTests}</p></div>
      )}
    </div>
  )
}
