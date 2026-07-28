'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';

import { loadDocsSearchEntries, type DocsSearchEntry } from '@/lib/docs/search';

const SEARCH_ATTR = 'data-docs-search-open';
const SEARCH_LISTBOX_ID = 'docs-search-results';
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function DocsSearch() {
  const [entries, setEntries] = useState<DocsSearchEntry[]>([]);
  const [searchStatus, setSearchStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const isOpenRef = useRef(false);
  const router = useRouter();

  // Load search index
  useEffect(() => {
    let active = true;
    loadDocsSearchEntries()
      .then((loadedEntries) => {
        if (!active) return;
        setEntries(loadedEntries);
        setSearchStatus('ready');
      })
      .catch(() => {
        if (!active) return;
        setEntries([]);
        setSearchStatus('error');
      });
    return () => {
      active = false;
    };
  }, []);

  // Watch attribute for open/close
  useEffect(() => {
    function syncOpenState() {
      const open = document.documentElement.hasAttribute(SEARCH_ATTR);

      if (open === isOpenRef.current) return;
      isOpenRef.current = open;

      if (open && document.activeElement instanceof HTMLElement) {
        returnFocusRef.current = document.activeElement;
      }

      setIsOpen(open);
      if (open) {
        setQuery('');
        setSelected(0);
      }
    }

    const obs = new MutationObserver(syncOpenState);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: [SEARCH_ATTR] });
    syncOpenState();
    return () => obs.disconnect();
  }, []);

  // Move focus into the dialog when it opens and return it when it closes.
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      return;
    }

    // The attribute observer may have queued an open state during this effect cycle.
    if (isOpenRef.current) return;

    const returnTarget = returnFocusRef.current;
    returnFocusRef.current = null;
    if (returnTarget?.isConnected) returnTarget.focus();
  }, [isOpen]);

  // Keep the page behind the modal inert and preserve its exact scroll position.
  useEffect(() => {
    if (!isOpen) return;

    const overlay = overlayRef.current;
    if (!overlay) return;

    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    const previousBodyStyles = {
      overflow: document.body.style.overflow,
      overscrollBehavior: document.body.style.overscrollBehavior,
      position: document.body.style.position,
      top: document.body.style.top,
      width: document.body.style.width,
    };
    const previousRootOverflow = document.documentElement.style.overflow;
    const backgroundElements = Array.from(document.body.children)
      .filter((element): element is HTMLElement => (
        element instanceof HTMLElement && element !== overlay
      ))
      .map((element) => ({
        element,
        inert: element.inert,
        ariaHidden: element.getAttribute('aria-hidden'),
      }));

    function containFocus(event: FocusEvent) {
      const target = event.target;
      if (target instanceof Node && !dialogRef.current?.contains(target)) {
        inputRef.current?.focus();
      }
    }

    backgroundElements.forEach(({ element }) => {
      element.inert = true;
      element.setAttribute('aria-hidden', 'true');
    });
    document.body.style.overflow = 'hidden';
    document.body.style.overscrollBehavior = 'contain';
    document.body.style.position = 'fixed';
    document.body.style.top = `-${scrollY}px`;
    document.body.style.width = '100%';
    document.documentElement.style.overflow = 'hidden';
    document.addEventListener('focusin', containFocus);

    return () => {
      document.removeEventListener('focusin', containFocus);
      backgroundElements.forEach(({ element, inert, ariaHidden }) => {
        element.inert = inert;
        if (ariaHidden === null) {
          element.removeAttribute('aria-hidden');
        } else {
          element.setAttribute('aria-hidden', ariaHidden);
        }
      });
      document.body.style.overflow = previousBodyStyles.overflow;
      document.body.style.overscrollBehavior = previousBodyStyles.overscrollBehavior;
      document.body.style.position = previousBodyStyles.position;
      document.body.style.top = previousBodyStyles.top;
      document.body.style.width = previousBodyStyles.width;
      document.documentElement.style.overflow = previousRootOverflow;
      window.scrollTo(scrollX, scrollY);
    };
  }, [isOpen]);

  // Cmd+K shortcut
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) {
          document.documentElement.removeAttribute(SEARCH_ATTR);
        } else {
          document.documentElement.setAttribute(SEARCH_ATTR, '1');
        }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen]);

  const q = query.toLowerCase().trim();
  const results = q
    ? entries
        .map((entry) => ({ entry, score: scoreEntry(entry, q) }))
        .filter((s) => s.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 12)
        .map((s) => s.entry)
    : [];
  const activeIndex = results.length > 0 ? Math.min(selected, results.length - 1) : -1;
  const activeOptionId = activeIndex >= 0 ? getOptionId(activeIndex) : undefined;

  function close() {
    document.documentElement.removeAttribute(SEARCH_ATTR);
  }

  function navigate(href: string) {
    close();
    router.push(href);
  }

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (results.length > 0) setSelected((s) => Math.min(s + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (results.length > 0) setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === 'Enter') {
      const result = results[activeIndex];
      if (result) {
        e.preventDefault();
        navigate(result.href);
      }
    }
  }

  function handleDialogKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close();
      return;
    }

    if (e.key !== 'Tab') return;

    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? []
    ).filter((element) => element.getAttribute('aria-hidden') !== 'true');
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (!first || !last) {
      e.preventDefault();
      dialogRef.current?.focus();
    } else if (e.shiftKey && (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  useEffect(() => {
    const el = resultsRef.current?.querySelector('[data-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  if (!isOpen) return null;

  return createPortal(
    <div ref={overlayRef} className="docs-search-overlay" onClick={close}>
      <div
        id="docs-search-dialog"
        ref={dialogRef}
        className="docs-search-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Search documentation"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleDialogKeyDown}
      >
        <div className="docs-search-input-row">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="docs-search-icon">
            <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10 10L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            className="docs-search-input"
            placeholder="Search docs..."
            role="combobox"
            aria-label="Search documentation"
            aria-autocomplete="list"
            aria-haspopup="listbox"
            aria-expanded={Boolean(q && results.length > 0)}
            aria-controls={q && results.length > 0 ? SEARCH_LISTBOX_ID : undefined}
            aria-activedescendant={activeOptionId}
            autoComplete="off"
            spellCheck="false"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(0); }}
            onKeyDown={handleInputKeyDown}
          />
          <button type="button" className="docs-search-close" aria-label="Close search" onClick={close}>
            <kbd aria-hidden="true">Esc</kbd>
          </button>
        </div>
        {(q || searchStatus === 'error') && (
          <div className="docs-search-body" ref={resultsRef}>
            {searchStatus === 'loading' ? (
              <div className="docs-search-empty" role="status">Loading documentation search&hellip;</div>
            ) : searchStatus === 'error' ? (
              <div className="docs-search-empty" role="alert">
                Documentation search is unavailable. Refresh the page and try again.
              </div>
            ) : results.length > 0 ? (
              <ul id={SEARCH_LISTBOX_ID} className="docs-search-results" role="listbox" aria-label="Search results">
                {results.map((r, i) => (
                  <li
                    key={r.href + r.title}
                    id={getOptionId(i)}
                    role="option"
                    aria-selected={i === activeIndex}
                    data-selected={i === activeIndex}
                    className={"docs-search-result" + (i === activeIndex ? " selected" : "")}
                    onClick={() => navigate(r.href)}
                    onMouseEnter={() => setSelected(i)}
                  >
                    <div className="docs-search-result-link">
                      <div className="docs-search-result-meta">
                        <span className="docs-search-result-section">{r.section}</span>
                      </div>
                      <div className="docs-search-result-title">{r.title}</div>
                      {r.content && (
                        <div className="docs-search-result-snippet">{r.content.slice(0, 120)}</div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="docs-search-empty" role="status">No results for &ldquo;{query}&rdquo;</div>
            )}
          </div>
        )}
        {results.length > 0 && (
          <div className="docs-search-hint">
            <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> Navigate</span>
            <span><kbd>Enter</kbd> Open</span>
            <span><kbd>Esc</kbd> Close</span>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

function getOptionId(index: number): string {
  return `${SEARCH_LISTBOX_ID}-option-${index}`;
}

function scoreEntry(entry: DocsSearchEntry, q: string): number {
  const title = entry.title.toLowerCase();
  const section = entry.section.toLowerCase();
  const content = entry.content.toLowerCase();
  if (title === q) return 100;
  if (title.startsWith(q)) return 80;
  if (title.includes(q)) return 60;
  if (section === q) return 50;
  if (section.includes(q)) return 30;
  if (content.includes(q)) return 10;
  return 0;
}
