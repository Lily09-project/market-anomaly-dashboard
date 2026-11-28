import type { ReactNode } from "react";

/**
 * A small set of line icons (24px grid, 2px round strokes) drawn inline: no icon
 * font or external request, so the CSP stays `img-src 'self'`. They take the
 * text colour (currentColor) and are always decorative: the label beside them
 * carries the meaning.
 */
const PATHS = {
  home: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>
  ),
  regimes: (
    <>
      <path d="m12 3 9 4.5-9 4.5-9-4.5Z" />
      <path d="m3 12 9 4.5 9-4.5" />
      <path d="m3 16.5 9 4.5 9-4.5" />
    </>
  ),
  events: <path d="M13 2 4 14h7l-1 8 9-12h-7Z" />,
  backtest: (
    <>
      <path d="M12 21s7.5-3.5 7.5-9.5V5.5L12 3 4.5 5.5v6C4.5 17.5 12 21 12 21Z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </>
  ),
  stress: <path d="M21 12h-3.5l-2.8 8L9.3 4l-2.8 8H3" />,
  market: (
    <>
      <path d="M3 3v18h18" />
      <path d="M8 17v-5" />
      <path d="M12.5 17V8" />
      <path d="M17 17v-7" />
    </>
  ),
  compare: (
    <>
      <path d="m8 3-4 4 4 4" />
      <path d="M4 7h16" />
      <path d="m16 13 4 4-4 4" />
      <path d="M20 17H4" />
    </>
  ),
  snapshot: (
    <>
      <path d="M14.5 4h-5L7.5 7H4a1.5 1.5 0 0 0-1.5 1.5v10A1.5 1.5 0 0 0 4 20h16a1.5 1.5 0 0 0 1.5-1.5v-10A1.5 1.5 0 0 0 20 7h-3.5Z" />
      <circle cx="12" cy="13.5" r="3.5" />
    </>
  ),
  data: (
    <>
      <path d="M14 2.5H6.5A1.5 1.5 0 0 0 5 4v16a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 20V7.5Z" />
      <path d="M14 2.5v5h5" />
      <path d="m9 15 2.2 2.2L15.5 13" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20.5 20.5-4.5-4.5" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export const hasIcon = (name: string): name is IconName => name in PATHS;

export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
