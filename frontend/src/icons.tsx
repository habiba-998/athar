import type { ReactNode } from 'react'

/** Small stroke icon set (24px grid). Decorative by default; pair with visible text. Direction-sensitive icons mirror in RTL. */
const P: Record<string, ReactNode> = {
  dashboard: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="4.5" rx="1.5" /><rect x="13.5" y="11.5" width="7" height="9" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /></>,
  graph: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="8" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8.3 7l7.3.7M7.2 8.2l3.6 7.6M16.9 10.2l-3.7 5.6" /></>,
  sliders: <><path d="M4 7h9M19 7h1M4 17h1M11 17h9" /><circle cx="16" cy="7" r="2.2" /><circle cx="8" cy="17" r="2.2" /></>,
  bulb: <path d="M9.5 18h5M10.5 21h3M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.2 1.1 2.2h5c0-1 .5-1.7 1.1-2.2A6 6 0 0 0 12 3z" />,
  database: <><ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" /><path d="M4.5 5.5v13c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-13M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.8-3.6 3.7-5.5 7-5.5s6.2 1.9 7 5.5" /></>,
  key: <><circle cx="8" cy="12" r="3.5" /><path d="M11.5 12H21M17 12v3M20 12v2" /></>,
  group: <><circle cx="9" cy="9" r="3" /><path d="M3 19c.6-3 3-4.6 6-4.6s5.4 1.6 6 4.6" /><circle cx="17" cy="10" r="2.4" /><path d="M16.5 14.6c2.5 0 4 1.3 4.5 3.6" /></>,
  server: <><rect x="3.5" y="4" width="17" height="6.5" rx="1.5" /><rect x="3.5" y="13.5" width="17" height="6.5" rx="1.5" /><path d="M7 7.25h.01M7 16.75h.01" /></>,
  cloud: <path d="M7 18a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 17.8 8.6 4.7 4.7 0 0 1 17.5 18z" />,
  shield: <path d="M12 3l7.5 2.8v5.7c0 4.6-3.1 7.9-7.5 9.5-4.4-1.6-7.5-4.9-7.5-9.5V5.8z" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  alert: <><path d="M12 4l9 15.5H3z" /><path d="M12 10v4.5M12 17.2v.01" /></>,
  arrow: <path d="M4 12h15M13.5 6.5L19 12l-5.5 5.5" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  undo: <><path d="M9 14L4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></>,
  upload: <><path d="M12 15V4M7.5 8.5L12 4l4.5 4.5" /><path d="M4.5 15v3.5h15V15" /></>,
  download: <><path d="M12 4v11M7.5 10.5L12 15l4.5-4.5" /><path d="M4.5 15v3.5h15V15" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  edit: <><path d="M4 20l1-4 11-11 3 3L8 19z" /><path d="M14 7l3 3" /></>,
  trash: <><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.5h9.4L17.5 7" /><path d="M10 11v5M14 11v5" /></>,
  filter: <path d="M4 5h16l-6 7.5V19l-4-2v-4.5z" />,
  lock: <><rect x="5" y="10.5" width="14" height="9.5" rx="2" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></>,
  globe: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.4 3.6 5.2 3.6 8.5s-1.1 6.1-3.6 8.5c-2.5-2.4-3.6-5.2-3.6-8.5S9.5 5.9 12 3.5z" /></>,
  scissors: <><circle cx="6.5" cy="7" r="2.5" /><circle cx="6.5" cy="17" r="2.5" /><path d="M8.7 8.3L20 18M8.7 15.7L20 6" /></>,
  list: <path d="M8.5 6.5H20M8.5 12H20M8.5 17.5H20M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01" />,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 7.8v.01" /></>,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></>,
  expand: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  compare: <><path d="M7 4v16M17 4v16" /><path d="M4 8h6M14 16h6" /></>,
  flask: <path d="M9.5 3h5M10.5 3v6L5 19a1.5 1.5 0 0 0 1.3 2.2h11.4A1.5 1.5 0 0 0 19 19l-5.5-10V3M7.5 15h9" />,
  layers: <path d="M12 4l8.5 4.5L12 13 3.5 8.5zM3.5 12.5L12 17l8.5-4.5M3.5 16.5L12 21l8.5-4.5" />,
  eye: <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.8" /></>,
}

const MIRROR = new Set(['arrow', 'chevron', 'undo'])

export type IconName = keyof typeof P

export function Icon({ name, size = 18, className = '' }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" className={`shrink-0 ${MIRROR.has(name) ? 'rtl:-scale-x-100' : ''} ${className}`}>
      {P[name]}
    </svg>
  )
}

export const TYPE_ICON: Record<string, IconName> = {
  user: 'user', service_account: 'key', group: 'group', server: 'server', database: 'database', cloud: 'cloud', control: 'shield', identity_provider: 'key',
}
