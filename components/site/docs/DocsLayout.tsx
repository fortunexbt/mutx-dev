'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useEffect, useRef } from 'react';
import { DocNavItem } from '@/lib/docs';
import { DocsNavContext, useDocsNav } from "./DocsNavContext";
import { DocsSearch } from "./DocsSearch";
import { DocsBreadcrumbs } from "./DocsBreadcrumbs";
import { useDocsLiveReload } from "./useDocsLiveReload";
import "@/app/docs/docs.css";

interface NavItemProps {
  item: DocNavItem;
  pathname: string;
}

interface DocsLayoutProps {
  nav: DocNavItem[];
  children: React.ReactNode;
  title?: string;
}

function navItemKey(slug: string) {
  return `docs-nav-open:${slug}`;
}

function NavItem({ item, pathname }: NavItemProps) {
  const hasChildren = item.children.length > 0;
  const [open, setOpen] = useState(false);
  const { onNavigate } = useDocsNav();

  // Hydrate from localStorage after mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(navItemKey(item.slug));
      if (stored !== null) setOpen(stored === 'true');
    } catch {
      // localStorage may be unavailable in SSR or restricted environments
    }
  }, [item.slug]);

  function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const next = !open;
    setOpen(next);
    try {
      localStorage.setItem(navItemKey(item.slug), String(next));
    } catch {
      // localStorage unavailable in SSR or restricted environments
    }
  }

  // Show expand chevron for ANY item with children (depth 0 or deeper)
  const showChevron = hasChildren;

  // Normalize pathname: strip trailing slash so /docs/api and /docs/api/ both match
  const normPath = pathname.replace(/\/$/, '');
  const itemPath = item.route;

  // Active if current pathname starts with this item's path (handles nested slugs)
  const isActive = normPath === itemPath || normPath.startsWith(itemPath + '/');

  // Determine if any descendant is active (for auto-expand)
  function isAncestorActive(items: DocNavItem[]): boolean {
    for (const child of items) {
      const childPath = child.route;
      const normChildPath = childPath.replace(/\/$/, '');
      if (
        normPath === normChildPath ||
        normPath.startsWith(normChildPath + '/')
      )
        return true;
      if (child.children.length > 0 && isAncestorActive(child.children))
        return true;
    }
    return false;
  }

  useEffect(() => {
    if (hasChildren && isAncestorActive(item.children)) {
      setOpen(true);
      try {
        localStorage.setItem(navItemKey(item.slug), 'true');
      } catch {
        // localStorage unavailable in SSR or restricted environments
      }
    }
  }, [pathname, hasChildren, item.children, item.slug]);

  // Lucide icon SVG paths for GitBook-style icons used in frontmatter
  const ICON_PATHS: Record<string, string> = {
    bullseye: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    'file-lines': '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    server: '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>',
    terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    'life-ring': '<circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/><path d="M3.05 11a9 9 0 0 1 .5-2.5"/><path d="M2 8a9 9 0 0 1 8-7"/><path d="M11.5 2a14.5 14.5 0 0 1 1 4"/><path d="M12 20a8 8 0 0 0 8-8"/>',
    handshake: '<path d="M11 17a4 4 0 0 0 5-5l-1-4-3 1.5"/><path d="M8 17a4 4 0 0 1 5-5l-1-4-3 1.5"/><path d="M11 17H2"/><path d="M22 17h-9"/><path d="M6 8l-4 4 4 4"/><path d="M18 8l4 4-4 4"/>',
    'user-shield': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    'scale-balanced': '<path d="M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z"/><path d="M2 16l3-8 3 8c-.87.65-1.92 1-3 1S1.13 16.65.24 16z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    'file-code': '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/>',
    road: '<path d="M4 19L8 5"/><path d="M16 5l4 14"/><path d="M12 5l4 14"/><path d="M4 19h16"/>',
    webhook: '<path d="M18 16.98h-5.99c-1.1 0-1.95.94-2.48 1.9A4 4 0 0 1 2 17c.01-.7.2-1.4.57-2"/><path d="m6 17 3.13-5.78c.53-.97.43-2.17-.26-3.14"/><path d="M2 17c.01-.7.2-1.4.57-2"/><path d="M22 14a2 2 0 1 0-4 0v2a8 8 0 0 1-4 7.96"/>',
    bookopen: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    'globe-alt': '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    chevron: '<polyline points="9 18 15 12 9 6"/>',
    home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    key: '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 0-7.778 7.778 5.5 5.5 0 0 0 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    unlock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
    git: '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
    github: '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/>',
    slack: '<path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z"/><path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/><path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z"/><path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z"/><path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z"/><path d="M15.5 19H14v1.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5-.67-1.5-1.5-1.5z"/><path d="M10 9.5C10 8.67 9.33 8 8.5 8h-5C2.67 8 2 8.67 2 9.5S2.67 11 3.5 11h5c.83 0 1.5-.67 1.5-1.5z"/><path d="M8.5 5H10V3.5C10 2.67 9.33 2 8.5 2S7 2.67 7 3.5 7.67 5 8.5 5z"/>',
    activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    alert: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    box: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    compass: '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    bookmark: '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    mail: '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
    map: '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
    navigation: '<polygon points="3 11 22 2 13 21 11 13 3 11"/>',
    'thumbs-up': '<path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>',
    'trending-up': '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    award: '<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>',
    'check-circle': '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    'alert-circle': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    'info': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    // --- Icons used in docs frontmatter but previously missing ---
    bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    bug: '<path d="M8 2h8"/><path d="M9 2a2 2 0 0 1 6 0"/><path d="M12 14v8"/><path d="M6 7a6 6 0 0 0 12 0"/><path d="M5.5 11.5L2 15"/><path d="M18.5 11.5L22 15"/><path d="M6 7h12"/>',
    'chart-line': '<path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/>',
    'circle-info': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    'circle-nodes': '<circle cx="12" cy="12" r="4"/><circle cx="4" cy="4" r="2"/><circle cx="20" cy="4" r="2"/><circle cx="4" cy="20" r="2"/><circle cx="20" cy="20" r="2"/><line x1="5.5" y1="5.5" x2="9" y2="9"/><line x1="18.5" y1="5.5" x2="15" y2="9"/><line x1="5.5" y1="18.5" x2="9" y2="15"/><line x1="18.5" y1="18.5" x2="15" y2="15"/>',
    cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    'diagram-project': '<path d="M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/><path d="M18 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/><path d="M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/><path d="M18 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/><line x1="9" y1="6" x2="15" y2="6"/><line x1="9" y1="18" x2="15" y2="18"/><line x1="6" y1="9" x2="6" y2="15"/><line x1="18" y1="9" x2="18" y2="15"/>',
    droplet: '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>',
    factory: '<path d="M2 20V8l5 4V8l5 4V4h8a2 2 0 0 1 2 2v14"/><path d="M2 20h20"/><path d="M12 14v6"/><path d="M17 14v6"/><path d="M7 14v6"/>',
    'flask-vial': '<path d="M5 3h6"/><path d="M8 3v6l-5 8h16L14 9V3"/><path d="M14.7 15a2 2 0 0 0-2.7 1.3 2 2 0 0 1-4-1.3"/>',
    inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    'layered-shapes': '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    microchip: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    plug: '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a6 6 0 0 1-12 0V8z"/>',
    question: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    robot: '<rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/>',
    rocket: '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
    'screwdriver-wrench': '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    'shield-halved': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="2" x2="12" y2="22"/>',
    sitemap: '<rect x="8" y="2" width="8" height="4" rx="1"/><rect x="1" y="16" width="6" height="4" rx="1"/><rect x="17" y="16" width="6" height="4" rx="1"/><line x1="12" y1="6" x2="12" y2="12"/><line x1="4" y1="16" x2="4" y2="12"/><line x1="20" y1="16" x2="20" y2="12"/><line x1="4" y1="12" x2="20" y2="12"/>',
    'tower-broadcast': '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
    train: '<rect x="4" y="3" width="16" height="16" rx="2"/><line x1="4" y1="11" x2="20" y2="11"/><circle cx="8" cy="15" r="1"/><circle cx="16" cy="15" r="1"/><path d="M6 19l-2 3"/><path d="M18 19l2 3"/>',
    wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  };

  function renderIcon(name: string | undefined) {
    if (!name) return null;
    const d = ICON_PATHS[name] || ICON_PATHS['file-lines'];
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="docs-nav-icon"
        dangerouslySetInnerHTML={{ __html: d }}
      />
    );
  }

  return (
    <div className="docs-nav-section">
      <div className={`docs-nav-row${hasChildren ? ' has-children' : ''}`}>
        {showChevron && (
          <button
            className={`docs-nav-chevron-btn${open ? ' open' : ''}`}
            onClick={toggle}
            aria-label={open ? 'Collapse' : 'Expand'}
            aria-expanded={open}
          >
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              aria-hidden="true"
              className="docs-nav-chevron-icon"
            >
              <path
                d="M2 3.5L5 6.5L8 3.5"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
        <Link
          href={item.route}
          className={`docs-nav-link${isActive ? ' active' : ''}${
            item.depth > 0 ? ' docs-nav-link-nested' : ''
          }`}
          style={{ paddingLeft: showChevron ? '4px' : `${item.depth * 16 + 16}px` }}
          onClick={() => onNavigate?.()}
          aria-current={isActive ? 'page' : undefined}
        >
          {renderIcon(item.icon)}
          <span className={item.icon ? 'docs-nav-label' : undefined}>{item.title}</span>
        </Link>
      </div>

      {hasChildren && open && (
        <div className="docs-nav-children">
          {item.children.map((child) => (
            <NavItem key={child.route} item={child} pathname={pathname} />
          ))}
        </div>
      )}
    </div>
  );
}

export function DocsLayout({ nav, children, title = 'MUTX' }: DocsLayoutProps) {
  useDocsLiveReload();
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const mobileSidebarRef = useRef<HTMLElement>(null);
  const docsContentRef = useRef<HTMLElement>(null);
  const docsHeaderRef = useRef<HTMLElement>(null);
  const hasSidebar = nav.length > 0;
  const editorialRoutes = ['/manifesto', '/whitepaper', '/roadmap'];
  const resourceRoutes = ['/infrastructure', '/sdk', '/security', '/support'];
  const isEditorial = editorialRoutes.includes(pathname);
  const isResource = resourceRoutes.includes(pathname);
  const isStandalone = isEditorial || isResource;
  const standaloneDescriptions: Record<string, string> = {
    '/manifesto': 'What MUTX believes about autonomous software, operational trust, and the work after the demo.',
    '/whitepaper': 'The architecture, operating model, and technical choices behind MUTX.',
    '/roadmap': 'What is shipping now, what comes next, and what remains deliberately out of scope.',
    '/infrastructure': 'The production foundation for running MUTX across containers, clusters, and monitored environments.',
    '/sdk': 'Build agents, deployments, keys, and webhooks with the MUTX Python client.',
    '/security': 'How to report a vulnerability, what the policy covers, and what happens next.',
    '/support': 'The fastest path to help with setup, bugs, security, or a product decision.',
  };
  const standaloneDescription = standaloneDescriptions[pathname] ?? '';
  const standaloneLinks = isEditorial
    ? [
        { label: 'Manifesto', href: '/manifesto' },
        { label: 'Whitepaper', href: '/whitepaper' },
        { label: 'Roadmap', href: '/roadmap' },
      ]
    : [
        { label: 'Infrastructure', href: '/infrastructure' },
        { label: 'Python SDK', href: '/sdk' },
        { label: 'Security', href: '/security' },
        { label: 'Support', href: '/support' },
      ];

  function handleNavigate() {
    setMobileNavOpen(false);
  }

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!hasSidebar) return;

    const desktopQuery = window.matchMedia('(min-width: 1024px)');
    const closeAtDesktop = (event: MediaQueryListEvent) => {
      if (event.matches) setMobileNavOpen(false);
    };

    desktopQuery.addEventListener('change', closeAtDesktop);
    return () => desktopQuery.removeEventListener('change', closeAtDesktop);
  }, [hasSidebar]);

  useEffect(() => {
    if (!mobileNavOpen || !hasSidebar) return;

    const focusableSelector =
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const headerElements = Array.from(docsHeaderRef.current?.children ?? []).filter(
      (element) => element !== mobileToggleRef.current,
    );
    const previousBodyOverflow = document.body.style.overflow;
    const previousRootOverflow = document.documentElement.style.overflow;
    const previousOverscrollBehavior = document.body.style.overscrollBehavior;

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        setMobileNavOpen(false);
        return;
      }

      if (event.key === 'Tab' && mobileSidebarRef.current) {
        const focusable = Array.from(
          mobileSidebarRef.current.querySelectorAll<HTMLElement>(focusableSelector),
        );
        if (!focusable.length) {
          event.preventDefault();
          mobileSidebarRef.current.focus();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    docsContentRef.current?.setAttribute('inert', '');
    headerElements.forEach((element) => element.setAttribute('inert', ''));
    document.body.style.overflow = 'hidden';
    document.body.style.overscrollBehavior = 'contain';
    document.documentElement.style.overflow = 'hidden';
    window.requestAnimationFrame(() => {
      const sidebar = mobileSidebarRef.current;
      sidebar?.querySelector<HTMLElement>(focusableSelector)?.focus();
      if (sidebar && !sidebar.contains(document.activeElement)) sidebar.focus();
    });
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
      docsContentRef.current?.removeAttribute('inert');
      headerElements.forEach((element) => element.removeAttribute('inert'));
      document.body.style.overflow = previousBodyOverflow;
      document.body.style.overscrollBehavior = previousOverscrollBehavior;
      document.documentElement.style.overflow = previousRootOverflow;
      if (window.matchMedia('(max-width: 1023px)').matches) {
        mobileToggleRef.current?.focus();
      }
    };
  }, [hasSidebar, mobileNavOpen]);

  return (
    <DocsNavContext.Provider value={{ nav, onNavigate: handleNavigate }}>
    <div
      className={`docs-shell${isStandalone ? ' docs-shell-standalone' : ''}${isResource ? ' docs-shell-resource' : ''}`}
      data-mobile-nav-open={mobileNavOpen ? '1' : undefined}
    >
      {/* ── Top header ── */}
      <header ref={docsHeaderRef} className="docs-header">
        {hasSidebar ? (
          <button
            ref={mobileToggleRef}
            type="button"
            className="docs-mobile-nav-toggle p-1.5 -ml-1.5 text-gb-text-2 hover:text-white transition-colors rounded"
            aria-label={mobileNavOpen ? 'Close documentation navigation' : 'Open documentation navigation'}
            aria-expanded={mobileNavOpen}
            aria-controls="docs-mobile-navigation"
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            <svg
              width="18"
              height="18"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d={mobileNavOpen ? 'M6 6l12 12M18 6L6 18' : 'M4 6h16M4 12h16M4 18h16'}
              />
            </svg>
          </button>
        ) : null}
        <Link href="/docs" className="docs-header-logo">
          <span className="docs-header-logo-mark" aria-hidden="true">
            <span className="docs-header-logo-mark-inner">M</span>
          </span>
          <span className="docs-header-logo-copy">
            <span className="docs-header-logo-title">MUTX Docs</span>
            <span className="docs-header-logo-meta">operator manual</span>
          </span>
        </Link>

        <div className="flex-1" />

        <button
          className="docs-search-trigger"
          onClick={() => document.documentElement.setAttribute('data-docs-search-open', '1')}
          aria-label="Search docs (Cmd+K)"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
          >
            <circle
              cx="6.5"
              cy="6.5"
              r="4.5"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <path
              d="M10 10L14 14"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <span className="docs-search-trigger-text">Search…</span>
          <kbd className="docs-search-kbd">⌘K</kbd>
        </button>

        <DocsSearch />

        <a
          href="https://github.com/mutx-dev/mutx-dev"
          target="_blank"
          rel="noopener noreferrer"
          className="docs-header-link"
        >
          GitHub
        </a>
        <span className="docs-header-divider" style={{ color: 'var(--gb-text-3)' }}>·</span>
        <Link href="/" className="docs-header-link">
          MUTX site
        </Link>
        <span className="docs-header-divider" style={{ color: 'var(--gb-text-3)' }}>·</span>
        <a href="https://pico.mutx.dev" target="_blank" rel="noopener noreferrer" className="docs-header-link">
          Pico beta
        </a>
      </header>

      {/* ── Body layout ── */}
      <div className="docs-layout">
        {hasSidebar ? (
          <>
            <button
              type="button"
              className="docs-sidebar-overlay docs-mobile-overlay"
              aria-hidden="true"
              tabIndex={-1}
              onClick={() => setMobileNavOpen(false)}
            />

            {/* ── Left sidebar ── */}
            <aside
              ref={mobileSidebarRef}
              id="docs-mobile-navigation"
              className="docs-sidebar docs-mobile-sidebar"
              aria-label="Documentation navigation"
              role={mobileNavOpen ? 'dialog' : undefined}
              aria-modal={mobileNavOpen ? true : undefined}
              tabIndex={-1}
            >
              <nav aria-label="Docs nav">
                {nav.map((item) => (
                  <NavItem key={item.route} item={item} pathname={pathname} />
                ))}
              </nav>
            </aside>
          </>
        ) : null}

        {/* ── Main content ── */}
        <main ref={docsContentRef} id="main-content" className="docs-content">
          <div className="docs-content-shell">
            <DocsBreadcrumbs />
            {isStandalone ? (
              <header className="docs-standalone-masthead">
                <div>
                  <p className="docs-standalone-kicker">MUTX / {title}</p>
                  <h1 className="docs-standalone-title">{title}</h1>
                  <p className="docs-standalone-description">{standaloneDescription}</p>
                </div>
                <nav className="docs-standalone-rail" aria-label={isEditorial ? 'MUTX long-form pages' : 'MUTX resources'}>
                  {standaloneLinks.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={pathname === item.href ? 'active' : undefined}
                      aria-current={pathname === item.href ? 'page' : undefined}
                    >
                      {item.label}
                    </Link>
                  ))}
                </nav>
              </header>
            ) : null}
            {children}
          </div>
        </main>
      </div>
    </div>
    </DocsNavContext.Provider>
  );
}
