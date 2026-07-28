'use client';

import { useEffect, useRef, useState } from 'react';

interface Heading {
  id: string;
  text: string;
  level: number;
}

interface JumpNavProps {
  headings: Heading[];
}

export function JumpNav({ headings }: JumpNavProps) {
  const [activeId, setActiveId] = useState<string>('');
  const [isOpen, setIsOpen] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (headings.length === 0) return;

    const headingElements = headings
      .map(({ id }) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];

    if (headingElements.length === 0) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        // Find the topmost visible heading
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      {
        rootMargin: '-80px 0px -60% 0px',
        threshold: 0,
      }
    );

    headingElements.forEach((el) => observerRef.current?.observe(el));

    return () => observerRef.current?.disconnect();
  }, [headings]);

  if (headings.length < 3) return null;

  return (
    <nav
      aria-label="On this page"
      className="jump-nav"
    >
      <button
        type="button"
        className="jump-nav-toggle"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        aria-controls="docs-jump-nav-list"
      >
        <span>On this page</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className={`jump-nav-chevron${isOpen ? ' open' : ''}`}
          aria-hidden="true"
        >
          <path
            d="M2 4L6 8L10 4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      <ol id="docs-jump-nav-list" className={`jump-nav-list${isOpen ? ' open' : ''}`}>
        {headings.map((heading) => (
          <li
            key={heading.id}
            className={`jump-nav-item level-${heading.level}${
              activeId === heading.id ? ' active' : ''
            }`}
          >
            <a
              href={`#${heading.id}`}
              className="jump-nav-link"
              onClick={() => setIsOpen(false)}
              aria-current={activeId === heading.id ? 'location' : undefined}
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
