import type { ReactNode } from 'react'
import { ExternalLink, MoreVertical, PlusSquare, Share } from 'lucide-react'

import type { InstallMethod } from '@/pwa/platform'

interface Step {
  icon: ReactNode
  text: ReactNode
}

const ICON = 'size-4 text-brand-700'

function stepsFor(method: InstallMethod): Step[] {
  switch (method) {
    case 'ios':
      return [
        { icon: <Share className={ICON} aria-hidden />, text: <>Нажмите <b>«Поделиться»</b> в панели Safari (внизу на iPhone, вверху на iPad).</> },
        { icon: <PlusSquare className={ICON} aria-hidden />, text: <>Выберите <b>«На экран „Домой“»</b> — пролистайте список, если пункта не видно.</> },
        { icon: <span className="text-xs font-bold text-brand-700">OK</span>, text: <>Нажмите <b>«Добавить»</b>. Okurmen Kids появится на экране «Домой» и откроется как приложение.</> },
      ]
    case 'macos-safari':
      return [
        { icon: <Share className={ICON} aria-hidden />, text: <>В меню Safari откройте <b>«Файл»</b> или нажмите <b>«Поделиться»</b>.</> },
        { icon: <PlusSquare className={ICON} aria-hidden />, text: <>Выберите <b>«Добавить в Dock»</b> и подтвердите.</> },
      ]
    case 'in-app':
      return [
        { icon: <MoreVertical className={ICON} aria-hidden />, text: <>Откройте меню этого окна (⋯ или ⋮).</> },
        { icon: <ExternalLink className={ICON} aria-hidden />, text: <>Выберите <b>«Открыть в браузере»</b> (Safari или Chrome) и установите приложение оттуда.</> },
      ]
    default:
      return [
        { icon: <MoreVertical className={ICON} aria-hidden />, text: <>Откройте меню браузера (⋮ в Chrome, ⋯ в Edge).</> },
        { icon: <PlusSquare className={ICON} aria-hidden />, text: <>Выберите <b>«Установить Okurmen Kids»</b> или <b>«Приложения → Установить»</b>.</> },
      ]
  }
}

/** Step-by-step manual installation for browsers without an install prompt. */
export function InstallInstructions({ method }: { method: InstallMethod }) {
  return (
    <ol className="space-y-3">
      {stepsFor(method).map((step, index) => (
        <li key={index} className="flex items-start gap-3 text-sm text-ink">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-50">{step.icon}</span>
          <span className="pt-1.5 leading-snug">{step.text}</span>
        </li>
      ))}
    </ol>
  )
}
