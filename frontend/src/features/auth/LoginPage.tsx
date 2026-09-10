import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Lock, User as UserIcon } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { useAuth } from '@/hooks/useAuth'

import { loginSchema, type LoginFormValues } from './loginSchema'

export function LoginPage() {
  const { status, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  if (status === 'authenticated') {
    const from = (location.state as { from?: Location } | null)?.from
    return <Navigate to={from?.pathname ?? '/app/dashboard'} replace />
  }

  async function onSubmit(values: LoginFormValues) {
    setFormError(null)
    try {
      await login(values.username, values.password)
      navigate('/app/dashboard', { replace: true })
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Не удалось войти. Проверьте логин и пароль.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="flex size-12 items-center justify-center rounded-xl bg-brand-500 text-lg font-bold text-white">
            OK
          </span>
          <h1 className="mt-4 text-lg font-semibold text-ink">OkurmenKIDS</h1>
          <p className="mt-1 text-sm text-ink-secondary">Кабинет тренера</p>
        </div>

        <form onSubmit={(event) => void handleSubmit(onSubmit)(event)} className="space-y-4" noValidate>
          <div>
            <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-ink">
              Логин
            </label>
            <div className="relative">
              <UserIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
              <input
                id="username"
                type="text"
                autoComplete="username"
                className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-ink focus-visible:border-brand-500"
                aria-invalid={Boolean(errors.username)}
                aria-describedby={errors.username ? 'username-error' : undefined}
                {...register('username')}
              />
            </div>
            {errors.username ? (
              <p id="username-error" className="mt-1 text-xs text-danger">
                {errors.username.message}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink">
              Пароль
            </label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-ink focus-visible:border-brand-500"
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? 'password-error' : undefined}
                {...register('password')}
              />
            </div>
            {errors.password ? (
              <p id="password-error" className="mt-1 text-xs text-danger">
                {errors.password.message}
              </p>
            ) : null}
          </div>

          {formError ? (
            <div role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {formError}
            </div>
          ) : null}

          <Button type="submit" className="w-full" isLoading={isSubmitting}>
            Войти
          </Button>
        </form>
      </div>
    </div>
  )
}
