import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, Lock, User as UserIcon } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import logo from '@/assets/logo.png'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage, isNetworkOrServerError } from '@/lib/apiError'
import { HOME_PATH } from '@/lib/appMode'
import { resolveReturnTo } from '@/lib/returnTo'
import { homeFor } from '@/lib/roles'

import { loginSchema, type LoginFormValues } from './loginSchema'

export function LoginPage() {
  const { status, login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  // Back to the page that sent the user here (e.g. the Schedule site), else the default home.
  const from = (location.state as { from?: Location } | null)?.from
  const target = resolveReturnTo(from ? `${from.pathname}${from.search ?? ''}` : null, HOME_PATH)

  if (status === 'authenticated') {
    return <Navigate to={homeFor(user?.role, target)} replace />
  }

  async function onSubmit(values: LoginFormValues) {
    setFormError(null)
    try {
      const me = await login(values.username, values.password)
      navigate(homeFor(me?.role, target), { replace: true })
    } catch (error) {
      if (isNetworkOrServerError(error)) {
        setFormError('Сервер недоступен. Проверьте подключение к интернету и попробуйте ещё раз.')
        return
      }
      const fallback = error instanceof Error ? error.message : 'Не удалось войти. Проверьте логин и пароль.'
      setFormError(extractErrorMessage(error, fallback))
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface-muted px-4">
      <div className="card w-full max-w-sm p-6 shadow-sm sm:p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src={logo} alt="OkurmenKIDS" className="size-20 shrink-0 object-contain" />
          <h1 className="mt-4 text-lg font-semibold text-ink">OkurmenKIDS</h1>
          <p className="mt-1 text-sm text-ink-secondary">Вход в LMS — тренеры и Team Lead</p>
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
                className="form-control pl-9"
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
                className="form-control pl-9"
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
