"use client";

import { useEffect, useRef } from "react";

interface DocsRendererClientProps {
  html: string;
}

function createCalloutIcon(type: string): SVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "docs-callout-icon");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("fill", "none");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");

  const addPath = (d: string, extra: Record<string, string> = {}) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.5");
    Object.entries(extra).forEach(([key, value]) => path.setAttribute(key, value));
    svg.appendChild(path);
  };

  const addCircle = () => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", "8");
    circle.setAttribute("cy", "8");
    circle.setAttribute("r", "6.5");
    circle.setAttribute("stroke", "currentColor");
    circle.setAttribute("stroke-width", "1.5");
    svg.appendChild(circle);
  };

  switch (type) {
    case "warning":
      addPath("M8 2L14 13H2L8 2Z", { "stroke-linejoin": "round" });
      addPath("M8 7v3M8 11.5v.5", { "stroke-linecap": "round" });
      break;
    case "danger":
      addCircle();
      addPath("M5.5 5.5l5 5M10.5 5.5l-5 5", { "stroke-linecap": "round" });
      break;
    case "tip":
      addPath("M8 2a4 4 0 011.5 7.75L11 11l-1 .25L9.5 12H8v4", {
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      });
      addPath("M6 6h.5M6 8h.5", { "stroke-linecap": "round" });
      break;
    case "note":
    default:
      addCircle();
      addPath("M8 7v4M8 5.5v.5", { "stroke-linecap": "round" });
      break;
  }

  return svg;
}

export function isSafeRenderedHref(value: string | null): value is string {
  if (!value) return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  const firstCodePoint = trimmed.charCodeAt(0);
  if (firstCodePoint <= 31 || firstCodePoint === 127 || trimmed.includes("\\")) return false;
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) return true;
  return /^https?:\/\//i.test(trimmed);
}

export function DocsRendererClient({ html }: DocsRendererClientProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const blockquotes = el.querySelectorAll<HTMLElement>("blockquote.docs-callout[data-type]");
    blockquotes.forEach((bq) => {
      if (bq.querySelector(":scope > .docs-callout-icon")) return;
      const mappedType = bq.dataset.type ?? "note";
      bq.prepend(createCalloutIcon(mappedType));
    });

    const cardTables = el.querySelectorAll<HTMLElement>("table[data-view='cards']");
    cardTables.forEach((table) => {
      const headers = Array.from(table.querySelectorAll<HTMLElement>("thead th"));
      const columnIndex = (label: string, fallback: number) => {
        const index = headers.findIndex((header) => header.textContent?.trim().toLowerCase() === label);
        return index >= 0 ? index : fallback;
      };
      const titleIndex = columnIndex("title", 0);
      const descriptionIndex = columnIndex("description", 1);
      const targetIndex = columnIndex("target", 2);
      const coverIndex = columnIndex("cover", 3);
      const rows = table.querySelectorAll<HTMLElement>("tbody tr");
      const cards: HTMLElement[] = [];

      rows.forEach((row, index) => {
        const cells = row.querySelectorAll<HTMLElement>("td");
        if (cells.length === 0) return;

        const titleEl = cells[titleIndex]?.querySelector("strong") || cells[titleIndex];
        const title = titleEl.textContent?.trim() ?? "";
        const targetLink = cells[targetIndex]?.querySelector("a");
        const rawHref = targetLink?.getAttribute("href") ?? "";
        const href = isSafeRenderedHref(rawHref) ? rawHref : null;
        const rawLabel = targetLink?.textContent?.trim() ?? cells[targetIndex]?.textContent?.trim() ?? title;
        const targetLabel = rawLabel.replace(/\.md$/, "").trim();
        const desc = cells[descriptionIndex]?.textContent?.trim() ?? "";
        const coverImg = cells[coverIndex]?.querySelector("img");
        const coverSrc = coverImg?.getAttribute("src");
        const safeCoverSrc = isSafeRenderedHref(coverSrc ?? null) ? coverSrc : null;

        const card = document.createElement(href ? "a" : "article");
        card.className = "docs-card";
        if (href) card.setAttribute("href", href);
        card.setAttribute("data-card-index", String(index));

        if (safeCoverSrc) {
          const wrap = document.createElement("div");
          wrap.className = "docs-card-img-wrap";
          const image = document.createElement("img");
          image.className = "docs-card-img";
          image.setAttribute("src", safeCoverSrc);
          image.setAttribute("alt", title);
          wrap.appendChild(image);
          card.appendChild(wrap);
        }

        const body = document.createElement("div");
        body.className = "docs-card-body";

        const titleNode = document.createElement("span");
        titleNode.className = "docs-card-title";
        titleNode.textContent = title;
        body.appendChild(titleNode);

        if (desc) {
          const descNode = document.createElement("span");
          descNode.className = "docs-card-desc";
          descNode.textContent = desc;
          body.appendChild(descNode);
        }

        if (href) {
          const targetNode = document.createElement("span");
          targetNode.className = "docs-card-target";
          targetNode.textContent = targetLabel;
          body.appendChild(targetNode);
        }

        card.appendChild(body);
        cards.push(card);
      });

      if (cards.length > 0) {
        const wrapper = document.createElement("div");
        wrapper.className = "docs-cards-grid";
        cards.forEach((card) => wrapper.appendChild(card));
        table.replaceWith(wrapper);
      }
    });

    const preBlocks = el.querySelectorAll<HTMLElement>("pre");
    preBlocks.forEach((pre) => {
      const code = pre.querySelector("code");
      const codeText = code?.innerText ?? pre.innerText ?? "";

      const existing = pre.querySelector(".docs-copy-btn");
      if (existing) existing.remove();

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "docs-copy-btn";
      btn.textContent = "Copy";
      btn.setAttribute("aria-label", "Copy code");

      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(codeText);
          btn.textContent = "Copied!";
          btn.classList.add("copied");
          setTimeout(() => {
            btn.textContent = "Copy";
            btn.classList.remove("copied");
          }, 2000);
        } catch {
          btn.textContent = "Failed";
          setTimeout(() => {
            btn.textContent = "Copy";
          }, 2000);
        }
      });

      pre.appendChild(btn);
    });
  }, [html]);

  return <article ref={ref} className="docs-prose" dangerouslySetInnerHTML={{ __html: html }} />;
}
