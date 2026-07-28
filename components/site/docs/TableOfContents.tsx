'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

interface Heading {
  id: string;
  text: string;
  level: number;
}

interface TableOfContentsProps {
  // headings extracted from raw markdown source
  sourceHeadings: Heading[];
}

export function TableOfContents({ sourceHeadings }: TableOfContentsProps) {
  const [activeId, setActiveId] = useState<string>('');
  const observerRef = useRef<IntersectionObserver | null>(null);

  // Map raw markdown headings to the IDs used in the rendered HTML.
  // remark strips emphasis from heading text and adds anchor links.
  // We derive the DOM IDs by slugifying the stripped text.
  const mappedHeadings = useMemo(
    () => sourceHeadings
      .filter((h) => h.level >= 2 && h.level <= 3)
      .map((h) => ({
        ...h,
        domId: h.id,
      })),
    [sourceHeadings],
  );

  useEffect(() => {
    const elements = mappedHeadings
      .map(({ domId }) => document.getElementById(domId))
      .filter(Boolean) as HTMLElement[];

    if (!elements.length) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      { rootMargin: '-80px 0px -70% 0px', threshold: 0 }
    );

    elements.forEach((el) => observerRef.current?.observe(el));
    return () => observerRef.current?.disconnect();
  }, [mappedHeadings]);

  if (mappedHeadings.length < 3) return null;

  return (
    <aside className="docs-toc">
      <p id="docs-toc-title" className="docs-toc-title">On this page</p>
      <nav aria-labelledby="docs-toc-title">
        {mappedHeadings.map((heading) => (
          <a
            key={heading.domId}
            href={`#${heading.domId}`}
            className={`docs-toc-link${heading.level === 3 ? ' docs-toc-link-nested' : ''}${
              activeId === heading.domId ? ' active' : ''
            }`}
            aria-current={activeId === heading.domId ? 'location' : undefined}
          >
            {heading.text}
          </a>
        ))}
      </nav>
    </aside>
  );
}
