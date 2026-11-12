import type { ReactNode } from 'react'

import type { Program } from '@/features/programs/programs'

/**
 * Inline SVG artwork for the six program cards (homepage «Популярные курсы»).
 * Drawn here instead of downloaded: nothing to load, crisp at any size, and
 * the same purple/yellow palette as the rest of the page.
 */
const BACKGROUNDS: Record<Program['id'], [string, string]> = {
  html: ['#4a2397', '#25105f'],
  python: ['#3d1c93', '#1c0c4d'],
  react: ['#5b2fc0', '#2b1468'],
  fastapi: ['#0f8f7e', '#064e46'],
  vibe: ['#4a2397', '#1c0c4d'],
  literacy: ['#c04fd8', '#6a2bb8'],
}

function Laptop({ x = 150, y = 34, w = 150, children }: { x?: number; y?: number; w?: number; children?: ReactNode }) {
  const h = w * 0.62
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="9" fill="#1b1240" stroke="#ffffff" strokeOpacity="0.18" />
      <rect x={x + 7} y={y + 7} width={w - 14} height={h - 14} rx="5" fill="#2b1a63" />
      {children}
      <path d={`M${x - 14} ${y + h + 2} H${x + w + 14} L${x + w + 4} ${y + h + 12} H${x - 4} Z`} fill="#d9d0f5" />
    </g>
  )
}

const codeLines = (x: number, y: number, widths: number[], colors = ['#ffb914', '#c9a7ff', '#7ee0c2', '#ffd9a0']) =>
  widths.map((w, i) => <rect key={i} x={x + (i % 2) * 10} y={y + i * 11} width={w} height="5" rx="2.5" fill={colors[i % colors.length]} opacity="0.85" />)

const ART: Record<Program['id'], ReactNode> = {
  html: (
    <>
      <Laptop>{codeLines(166, 50, [56, 80, 44, 70])}</Laptop>
      <g transform="translate(176 96) rotate(-6)">
        <rect width="92" height="38" rx="9" fill="#ff5a4e" />
        <text x="46" y="27" textAnchor="middle" fontFamily="Nunito, sans-serif" fontWeight="900" fontSize="24" fill="#fff">HTML</text>
      </g>
      <text x="44" y="70" fontFamily="monospace" fontWeight="700" fontSize="34" fill="#ffb914">{'</>'}</text>
      <text x="58" y="110" fontFamily="monospace" fontWeight="700" fontSize="20" fill="#c9a7ff">{'{ }'}</text>
    </>
  ),
  python: (
    <>
      <Laptop x={170} y={30} w={130}>{codeLines(184, 46, [40, 62, 34, 54])}</Laptop>
      <g transform="translate(60 26) scale(1.05)">
        <path d="M48 4c-22 0-21 9-21 9v10h22v4H17S4 25 4 47s11 21 11 21h7V57s0-12 12-12h22s11 0 11-11V15S69 4 48 4Zm-12 7a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z" fill="#3b82c4" />
        <path d="M49 98c22 0 21-9 21-9V79H48v-4h32s13 2 13-20-11-21-11-21h-7v11s0 12-12 12H41s-11 0-11 11v19s-3 11 19 11Zm12-7a4 4 0 1 1 0-8 4 4 0 0 1 0 8Z" fill="#ffd43b" />
      </g>
    </>
  ),
  react: (
    <>
      <Laptop x={40} y={40} w={120}>{codeLines(52, 54, [36, 52, 30])}</Laptop>
      <g transform="translate(232 80)" fill="none" stroke="#61dafb" strokeWidth="6">
        <ellipse rx="58" ry="22" />
        <ellipse rx="58" ry="22" transform="rotate(60)" />
        <ellipse rx="58" ry="22" transform="rotate(120)" />
        <circle r="10" fill="#61dafb" stroke="none" />
      </g>
    </>
  ),
  fastapi: (
    <>
      <circle cx="96" cy="80" r="44" fill="#05998b" stroke="#ffffff" strokeOpacity="0.35" strokeWidth="3" />
      <path d="M104 44 L74 88 H96 L88 116 L120 70 H98 Z" fill="#ffffff" />
      <text x="156" y="92" fontFamily="Nunito, sans-serif" fontWeight="900" fontSize="34" fill="#ffffff">FastAPI</text>
      {codeLines(158, 108, [70, 50], ['#7ee0c2', '#ffffff'])}
    </>
  ),
  vibe: (
    <>
      <g transform="translate(110 30)">
        {[0, 1, 2, 3].map((i) => (
          <g key={i} fill="#c9a7ff">
            <rect x={14 + i * 20} y="-12" width="6" height="14" rx="3" />
            <rect x={14 + i * 20} y="98" width="6" height="14" rx="3" />
            <rect x="-12" y={14 + i * 20} width="14" height="6" rx="3" />
            <rect x="98" y={14 + i * 20} width="14" height="6" rx="3" />
          </g>
        ))}
        <rect width="100" height="100" rx="18" fill="#5b2fc0" stroke="#c9a7ff" strokeWidth="4" />
        <text x="50" y="66" textAnchor="middle" fontFamily="Nunito, sans-serif" fontWeight="900" fontSize="42" fill="#ffb914">AI</text>
      </g>
      <path d="M46 46 l6 14 14 6 -14 6 -6 14 -6 -14 -14 -6 14 -6 Z" fill="#ffb914" />
      <path d="M262 98 l4 9 9 4 -9 4 -4 9 -4 -9 -9 -4 9 -4 Z" fill="#ffffff" opacity="0.9" />
    </>
  ),
  literacy: (
    <>
      <Laptop x={90} y={30} w={150}>
        <rect x="104" y="44" width="40" height="30" rx="4" fill="#ffb914" />
        <rect x="150" y="44" width="40" height="30" rx="4" fill="#c9a7ff" />
        <rect x="196" y="44" width="30" height="30" rx="4" fill="#7ee0c2" />
        {codeLines(104, 82, [90, 60], ['#ffffff', '#ffd9a0'])}
      </Laptop>
      <circle cx="52" cy="54" r="16" fill="#ffffff" opacity="0.2" />
      <circle cx="286" cy="118" r="12" fill="#ffb914" opacity="0.9" />
    </>
  ),
}

export function ProgramArt({ id }: { id: Program['id'] }) {
  const [from, to] = BACKGROUNDS[id]
  const gid = `program-bg-${id}`
  return (
    <svg viewBox="0 0 320 160" className="size-full" aria-hidden preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={from} />
          <stop offset="1" stopColor={to} />
        </linearGradient>
      </defs>
      <rect width="320" height="160" fill={`url(#${gid})`} />
      <circle cx="300" cy="10" r="60" fill="#ffffff" opacity="0.06" />
      <circle cx="10" cy="160" r="50" fill="#ffffff" opacity="0.05" />
      {ART[id]}
    </svg>
  )
}
