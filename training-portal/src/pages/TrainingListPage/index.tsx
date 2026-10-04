import { getTests } from '@/api/tests'
import { ErrorState } from '@/components/ErrorState'
import { Icon } from '@/components/Icon'
import { Loader } from '@/components/Loader'
import { TestCard } from '@/components/TestCard'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { storageService } from '@/services/storageService'

export function TrainingListPage() {
  const { data, loading, error, reload } = useAsync(getTests)
  return (
    <div className="container" style={{ paddingBottom: 80 }}>
      <header className="page-head">
        <h1 className="page-title">{t.home.testsTitle}</h1>
        <p className="section-subtitle">{t.home.testsSubtitle}</p>
      </header>
      {loading ? <Loader /> : error ? <ErrorState error={error} onRetry={reload} /> : data?.length ? (
        <div className="grid-cards">
          {data.map((test) => (
            <TestCard key={test.id} test={test} inProgress={Boolean(storageService.getActiveAttempt(test.id))} />
          ))}
        </div>
      ) : (
        <div className="empty"><Icon name="clipboard" /><p>{t.home.noTests}</p></div>
      )}
    </div>
  )
}
