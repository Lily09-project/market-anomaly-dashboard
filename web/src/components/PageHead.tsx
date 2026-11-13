import type { ReactNode } from "react";

/**
 * A page's opening block. It holds only static copy, so the heading paints
 * before any data file arrives; data-driven text belongs inside the page's Gate.
 */
export function PageHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="page-head">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      {children && <p className="lede">{children}</p>}
    </header>
  );
}
