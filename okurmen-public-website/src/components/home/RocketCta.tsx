import { Reveal } from '@/components/shared/Reveal'
import { EnrollButton } from '@/features/enrollment/EnrollButton'
import { useI18n } from '@/i18n'

/** A shaded 3D-style rocket with clouds — inline SVG, nothing to download. */
function Rocket() {
  return (
    <svg viewBox="0 0 320 240" className="h-full w-full" aria-hidden>
      <defs>
        <linearGradient id="rk-body" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#ffffff" /><stop offset="0.55" stopColor="#ece6fb" /><stop offset="1" stopColor="#b9a8ea" />
        </linearGradient>
        <linearGradient id="rk-fin" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8a63dc" /><stop offset="1" stopColor="#381a80" />
        </linearGradient>
        <radialGradient id="rk-window" cx="0.35" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#8fd3ff" /><stop offset="0.6" stopColor="#4a2397" /><stop offset="1" stopColor="#25105f" />
        </radialGradient>
        <linearGradient id="rk-flame" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff3c4" /><stop offset="0.45" stopColor="#ffb914" /><stop offset="1" stopColor="#ff7a1a" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="rk-cloud" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" /><stop offset="1" stopColor="#d9cff5" />
        </linearGradient>
      </defs>
      {/* trail */}
      <path d="M40 210 C 90 190, 120 170, 150 140" stroke="#ffb914" strokeWidth="5" strokeLinecap="round" fill="none" opacity="0.55" />
      {/* stars */}
      <path d="M262 36 l4 10 10 4 -10 4 -4 10 -4 -10 -10 -4 10 -4 Z" fill="#ffb914" />
      <circle cx="60" cy="58" r="4" fill="#ffffff" opacity="0.7" />
      <circle cx="292" cy="120" r="3" fill="#ffffff" opacity="0.6" />
      <g transform="translate(176 112) rotate(45)">
        {/* flame */}
        <path d="M-14 62 C -14 92, 0 118, 0 128 C 0 118, 14 92, 14 62 Z" fill="url(#rk-flame)" className="motion-safe:animate-pulse" />
        {/* fins */}
        <path d="M-24 30 L-46 66 L-22 58 Z" fill="url(#rk-fin)" />
        <path d="M24 30 L46 66 L22 58 Z" fill="url(#rk-fin)" />
        {/* body */}
        <path d="M0 -78 C 30 -50, 30 20, 22 62 H -22 C -30 20, -30 -50, 0 -78 Z" fill="url(#rk-body)" />
        <path d="M0 -78 C 14 -64, 22 -46, 25 -30 H -25 C -22 -46, -14 -64, 0 -78 Z" fill="#ffb914" />
        <circle cy="-8" r="15" fill="#ffffff" />
        <circle cy="-8" r="11" fill="url(#rk-window)" />
        <circle cx="-4" cy="-12" r="3" fill="#ffffff" opacity="0.8" />
        <rect x="-22" y="52" width="44" height="10" rx="3" fill="#8a63dc" />
        <path d="M-6 30 L0 62 L6 30 Z" fill="url(#rk-fin)" />
      </g>
      {/* clouds */}
      <g fill="url(#rk-cloud)">
        <path d="M10 236 C 0 210, 30 196, 50 206 C 58 184, 92 182, 104 202 C 122 194, 146 206, 140 236 Z" />
        <path d="M150 240 C 146 222, 166 212, 182 220 C 192 204, 220 206, 226 222 C 240 216, 258 226, 254 240 Z" opacity="0.9" />
      </g>
    </svg>
  )
}

/** Homepage closing call to action — opens the existing enrollment dialog. */
export function RocketCta({ title }: { title?: string }) {
  const { t } = useI18n()
  return (
    <section className="mx-auto w-full max-w-[1280px] px-4 pt-8 pb-14 sm:px-6 lg:px-8 lg:pt-10 lg:pb-20">
      <Reveal>
        <div className="relative grid items-center overflow-hidden rounded-[2rem] bg-gradient-to-br from-kids-primary via-[#3d1c93] to-kids-deep px-6 py-8 shadow-[0_30px_60px_-30px_rgb(37_16_95/0.7)] sm:px-10 md:grid-cols-[0.85fr_1.15fr] md:gap-6 md:py-6 lg:px-14">
          <div aria-hidden className="absolute -top-20 right-[-4rem] size-72 rounded-full bg-kids-yellow/15 blur-3xl" />
          <div aria-hidden className="absolute -bottom-16 left-1/3 size-56 rounded-full bg-brand-400/25 blur-3xl" />
          <div className="relative mx-auto h-44 w-full max-w-[22rem] sm:h-56 md:h-64 md:max-w-none motion-safe:animate-float">
            <Rocket />
          </div>
          <div className="relative py-2 text-center md:py-8 md:text-left">
            <h2 className="font-display text-[1.75rem] leading-tight font-black text-white sm:text-4xl">{title || t('home.rocket.title')}</h2>
            <p className="mx-auto mt-3 max-w-md text-base text-white/80 sm:text-lg md:mx-0">{t('home.rocket.text')}</p>
            <div className="mt-6 flex justify-center md:justify-start">
              <EnrollButton size="lg" label={t('home.rocket.button')} />
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  )
}
