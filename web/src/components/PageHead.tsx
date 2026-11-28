import type { ReactNode } from "react";
import { useRoute } from "../app/hooks";
import { hasIcon, Icon } from "./Icon";

/**
 * A page's opening block. It holds only static copy, so the heading paints
 * before any data file arrives; data-driven text belongs inside the page's Gate.
 * The title carries the same icon as the page's navigation entry.
 */
export function PageHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  const [route] = useRoute();
  return (
    <header className="page-head">
      <p className="eyebrow">{eyebrow}</p>
      <h1>
        {hasIcon(route.name) && (
          <span className="page-icon">
            <Icon name={route.name} size={24} />
          </span>
        )}
        {title}
      </h1>
      {children && <p className="lede">{children}</p>}
    </header>
  );
}
