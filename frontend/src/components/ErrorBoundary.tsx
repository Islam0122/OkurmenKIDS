import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { AlertOctagon } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { FullScreenStatus } from '@/components/ui/FullScreenStatus'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * The outermost safety net: catches render errors thrown by anything above
 * `<RouterProvider>` (providers, context setup) that React Router's own
 * `errorElement` never sees, since that only covers the routed tree beneath
 * it. Without this, such an error would otherwise unmount the whole app
 * into a blank white page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error('Top-level error boundary caught:', error, info.componentStack)
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <FullScreenStatus
          icon={AlertOctagon}
          tone="danger"
          title="Что-то пошло не так"
          description="Приложению не удалось загрузиться. Попробуйте обновить страницу."
          actions={<Button onClick={() => window.location.reload()}>Обновить страницу</Button>}
        />
      )
    }

    return this.props.children
  }
}
