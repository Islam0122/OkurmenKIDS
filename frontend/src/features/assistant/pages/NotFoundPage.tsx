import { Compass } from 'lucide-react'

import { EmptyState } from '@/components/ui/EmptyState'

import { ButtonLink } from '../ui'

/** An unknown /assistant/* address — inside the workspace shell, not a full-screen page. */
export function AssistantNotFoundPage() {
  return <EmptyState icon={Compass} title="Страница не найдена" description="Такого раздела в Assistant Workspace нет." action={<ButtonLink to="/assistant">На Dashboard</ButtonLink>} />
}
