import { Loader } from '@/components/Loader'
import { TestCard } from '@/components/TestCard'
import { useAsync } from '@/hooks/useAsync'
import { t } from '@/i18n'
import { contentService } from '@/services/contentService'
import { trainingService } from '@/services/trainingService'

export function TrainingListPage() {
  const { data, loading } = useAsync(() => contentService.getTests())
  return (
    <div className="container">
      <header className="page-head">
        <h1 className="page-title">{t.home.testsTitle}</h1>
        <p className="section-subtitle">{t.home.testsSubtitle}</p>
      </header>
      {loading ? <Loader /> : (
        <div className="grid-cards" style={{ paddingBottom: 80 }}>
          {(data ?? []).map((test) => (
            <TestCard key={test.id} test={test} inProgress={Boolean(trainingService.getProgress(test.id))} />
          ))}
        </div>
      )}
    </div>
  )
}
