import type { ReactNode } from "react";

/** A scrollable table wrapper that keyboard users can focus and scroll. */
export function ScrollRegion({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className ? `table-scroll ${className}` : "table-scroll"} role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
