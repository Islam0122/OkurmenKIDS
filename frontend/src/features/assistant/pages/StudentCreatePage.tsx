import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Card } from '@/components/ui/Card'

import { StudentForm } from '../actions/StudentForm'

/** The full-page «Добавить студента» (the same form as the quick modal). */
export function AssistantStudentCreatePage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  return (
    <div className="mx-auto max-w-2xl">
      <BackLink to="/assistant/students">К списку студентов</BackLink>
      <PageHeader title="Добавить студента" description="Студент сразу становится активным в выбранной группе." />
      <Card><StudentForm presetGroup={params.get('group') ?? ''} onCancel={() => navigate('/assistant/students')} /></Card>
    </div>
  )
}
