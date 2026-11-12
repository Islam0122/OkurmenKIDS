import { Check, Code2 } from 'lucide-react'

import { useI18n } from '@/i18n'

/**
 * The homepage hero illustration: a laptop with a dark-purple Python editor,
 * a «project launched» notification and a floating card. Pure HTML/CSS/SVG —
 * no image download, so it never delays the first paint (LCP). Decorative
 * shapes are aria-hidden; the figure has a text alternative.
 */
export function LaptopIllustration() {
  const { t } = useI18n()
  const hello = t('home.hero.codeHello')
  return (
    <figure className="relative mx-auto w-full max-w-[680px] select-none lg:-mr-4" aria-label={t('home.hero.illustration')}>
      {/* background shapes */}
      <div aria-hidden className="absolute top-[4%] left-[2%] h-[78%] w-[62%] rounded-[46%_54%_42%_58%/55%_45%_55%_45%] bg-kids-yellow" />
      <div aria-hidden className="absolute top-[-2%] right-[-2%] h-[86%] w-[72%] rounded-[58%_42%_50%_50%/45%_55%_45%_55%] bg-gradient-to-br from-brand-300 via-brand-500 to-kids-primary opacity-90" />
      <svg aria-hidden viewBox="0 0 60 40" className="absolute top-[6%] left-[-1%] w-12 text-kids-yellow sm:w-14">
        <path d="M6 30 L18 8 M26 32 L34 4 M44 30 L56 14" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
      </svg>

      <div className="relative px-[4%] pt-[7%] pb-[11%] motion-safe:animate-float">
        {/* screen */}
        <div className="relative rounded-[1.4rem] bg-[#1b1240] p-[2.2%] shadow-[0_40px_70px_-30px_rgb(37_16_95/0.65)] ring-1 ring-white/10">
          <div className="overflow-hidden rounded-[1rem] bg-gradient-to-b from-[#2b1a63] to-kids-deep">
            <div aria-hidden className="flex items-center gap-1.5 border-b border-white/10 px-4 py-2.5">
              <span className="size-2.5 rounded-full bg-[#ff6b6b]" />
              <span className="size-2.5 rounded-full bg-kids-yellow" />
              <span className="size-2.5 rounded-full bg-[#4ade80]" />
              <span className="ml-3 rounded-md bg-white/10 px-2.5 py-0.5 font-mono text-[11px] text-white/80">main.py</span>
            </div>
            <pre aria-hidden className="px-4 pt-3 pb-2 font-mono text-[11px] leading-[1.9] text-white sm:px-6 sm:text-[13px] lg:text-[13.5px]">
              <span className="block text-[#9d8fd0]">{t('home.hero.codeComment')}</span>
              <span className="block"><span className="text-kids-yellow">print</span>(<span className="text-[#ffd9a0]">"{hello}, Okurmen Kids!"</span>)</span>
              <span className="block">&nbsp;</span>
              <span className="block"><span className="text-[#c9a7ff]">for</span> i <span className="text-[#c9a7ff]">in</span> <span className="text-kids-yellow">range</span>(<span className="text-[#7ee0c2]">3</span>):</span>
              <span className="block pl-[4ch]"><span className="text-kids-yellow">print</span>(<span className="text-[#ffd9a0]">f"{t('home.hero.codeLoop')}: {'{'}i+1{'}'}"</span>)</span>
            </pre>
            <div className="px-4 pb-4 sm:px-6 sm:pb-5">
              <span className="inline-flex items-center gap-2 rounded-lg bg-[#16a34a]/20 px-3 py-1.5 text-[11px] font-semibold text-[#86efac] ring-1 ring-[#4ade80]/30 sm:text-xs">
                <Check className="size-3.5" strokeWidth={3} aria-hidden />
                {t('home.hero.toast')}
              </span>
            </div>
          </div>
        </div>
        {/* keyboard deck */}
        <div aria-hidden className="relative mx-[-5%] h-[18px] rounded-b-[1.6rem] rounded-t-md bg-gradient-to-b from-[#e8e2f8] to-[#c9bdef] shadow-[0_18px_30px_-14px_rgb(37_16_95/0.45)] sm:h-[22px]">
          <span className="absolute top-0 left-1/2 h-1.5 w-[16%] -translate-x-1/2 rounded-b-lg bg-[#b6a8e6]" />
        </div>
        {/* 3D cursor */}
        <svg aria-hidden viewBox="0 0 48 48" className="absolute right-[3%] bottom-[22%] w-11 drop-shadow-[0_8px_10px_rgb(37_16_95/0.35)] sm:w-14">
          <defs>
            <linearGradient id="cursor-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#b293f2" /><stop offset="1" stopColor="#4a2397" /></linearGradient>
          </defs>
          <path d="M6 4 L42 22 L26 26 L18 42 Z" fill="url(#cursor-g)" stroke="#fff" strokeWidth="2.5" strokeLinejoin="round" />
        </svg>
      </div>

      {/* floating card */}
      <figcaption className="absolute right-[2%] bottom-[2%] flex items-center gap-3 rounded-2xl bg-white px-3.5 py-2.5 shadow-[0_18px_40px_-16px_rgb(37_16_95/0.45)] sm:px-4 sm:py-3">
        <span className="grid size-9 place-items-center rounded-xl bg-kids-yellow text-kids-deep sm:size-10"><Code2 className="size-5" aria-hidden /></span>
        <span className="max-w-[9rem] font-display text-sm leading-tight font-extrabold text-kids-text">{t('home.hero.card')}</span>
      </figcaption>
    </figure>
  )
}
