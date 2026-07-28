import Link from "next/link";
import { flatNav, parseSummary } from "@/lib/docs";
import { DocNavItem } from "@/lib/docs";

interface PrevNext {
  prev: DocNavItem | null;
  next: DocNavItem | null;
}

function getPrevNext(currentRoute: string): PrevNext {
  const all = flatNav(parseSummary());
  const idx = all.findIndex((item) => item.route === currentRoute);
  return {
    prev: idx > 0 ? all[idx - 1] : null,
    next: idx >= 0 && idx < all.length - 1 ? all[idx + 1] : null,
  };
}

interface PrevNextNavProps {
  currentRoute: string;
}

export function PrevNextNav({ currentRoute }: PrevNextNavProps) {
  const { prev, next } = getPrevNext(currentRoute);

  if (!prev && !next) return null;

  return (
    <nav className="docs-prev-next" aria-label="Article navigation">
      <div className="docs-prev-next-inner">
        {prev ? (
          <Link href={prev.route} className="docs-prev-next-link docs-prev-link">
            <span className="docs-prev-next-label">
              <svg className="docs-directional-icon" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M9 11L5 7l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Previous
            </span>
            <span className="docs-prev-next-title">{prev.title}</span>
          </Link>
        ) : (
          <div />
        )}

        {next ? (
          <Link href={next.route} className="docs-prev-next-link docs-next-link">
            <span className="docs-prev-next-label">
              Next
              <svg className="docs-directional-icon" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </span>
            <span className="docs-prev-next-title">{next.title}</span>
          </Link>
        ) : (
          <div />
        )}
      </div>
    </nav>
  );
}
