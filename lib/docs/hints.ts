/**
 * Convert the small GitBook syntax subset used by published MUTX docs into
 * Markdown before parsing. Arbitrary source HTML remains disabled downstream.
 */

const HINT_LABELS: Record<string, string> = {
  info: "NOTE",
  warning: "WARNING",
  danger: "DANGER",
  tip: "TIP",
};

function quoteMarkdown(content: string): string {
  return content
    .trim()
    .split("\n")
    .map((line) => `> ${line}`.trimEnd())
    .join("\n");
}

/** Convert GitBook liquid hints to GitHub-alert-style Markdown blockquotes. */
export function preprocessHints(source: string): string {
  const hintRegex = /{%\s*hint\s+style=["']([^"']+)["']\s*%}([\s\S]*?){%\s*endhint\s*%}/g;

  return source.replace(hintRegex, (_match, style: string, content: string) => {
    const label = HINT_LABELS[style.toLowerCase()] ?? HINT_LABELS.info;
    const quotedContent = quoteMarkdown(content);
    return `> [!${label}]${quotedContent ? `\n${quotedContent}` : ""}`;
  });
}

const HTML_ENTITIES: Record<string, string> = {
  "&nbsp;": " ",
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
  "&apos;": "'",
};

function decodeHtmlEntities(value: string): string {
  return value.replace(/&(nbsp|amp|lt|gt|quot|#39|apos);/gi, (entity) => {
    return HTML_ENTITIES[entity.toLowerCase()] ?? entity;
  });
}

function htmlText(value: string): string {
  return decodeHtmlEntities(
    value
      .replace(/<(script|style|iframe|object|embed)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
      .replace(/<[^>]*>/g, " "),
  )
    .replace(/\s+/g, " ")
    .trim();
}

function markdownCell(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();
}

function attribute(tag: string, name: string): string | null {
  const match = tag.match(new RegExp(`\\b${name}\\s*=\\s*["']([^"']*)["']`, "i"));
  return match?.[1] ?? null;
}

interface HtmlCell {
  tag: string;
  content: string;
  text: string;
}

function cellsFromRow(row: string, tagName: "th" | "td"): HtmlCell[] {
  const cells: HtmlCell[] = [];
  const regex = new RegExp(`<${tagName}\\b([^>]*)>([\\s\\S]*?)<\\/${tagName}>`, "gi");
  for (const match of row.matchAll(regex)) {
    cells.push({ tag: match[1], content: match[2], text: htmlText(match[2]) });
  }
  return cells;
}

function rowMatches(section: string): string[] {
  return Array.from(section.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi), (match) => match[1]);
}

function linkFromCell(cell: HtmlCell | undefined): { href: string; label: string } | null {
  if (!cell) return null;
  const match = cell.content.match(/<a\b([^>]*)>([\s\S]*?)<\/a>/i);
  if (!match) return null;
  const href = attribute(match[1], "href");
  if (!href) return null;
  return { href, label: htmlText(match[2]) || href };
}

function imageFromCell(cell: HtmlCell | undefined): { src: string; alt: string } | null {
  if (!cell) return null;
  const match = cell.content.match(/<img\b([^>]*)\/?\s*>/i);
  if (!match) return null;
  const src = attribute(match[1], "src");
  if (!src) return null;
  return { src, alt: attribute(match[1], "alt") ?? "" };
}

/**
 * Convert only `<table data-view="cards">` into a normalized GFM table. The
 * allowlist extracts text, one target link, and one cover image; scripts,
 * handlers, styles, and every other raw tag are discarded as data.
 */
export function preprocessGitBookCardTables(source: string): string {
  const cardTableRegex = /<table\b(?=[^>]*\bdata-view\s*=\s*["']cards["'])[^>]*>([\s\S]*?)<\/table>/gi;

  return source.replace(cardTableRegex, (_table, inner: string) => {
    const head = inner.match(/<thead\b[^>]*>([\s\S]*?)<\/thead>/i)?.[1] ?? "";
    const body = inner.match(/<tbody\b[^>]*>([\s\S]*?)<\/tbody>/i)?.[1] ?? inner;
    const headerCells = cellsFromRow(rowMatches(head)[0] ?? "", "th");
    const titleIndex = Math.max(0, headerCells.findIndex((cell) => /^title$/i.test(cell.text)));
    const descriptionIndex = headerCells.findIndex((cell) => /^description$/i.test(cell.text));
    const targetIndex = headerCells.findIndex((cell) => /\bdata-card-target\b/i.test(cell.tag));
    const coverIndex = headerCells.findIndex((cell) => /\bdata-card-cover\b/i.test(cell.tag));

    const rows = rowMatches(body).map((row) => {
      const cells = cellsFromRow(row, "td");
      const target = linkFromCell(cells[targetIndex >= 0 ? targetIndex : 1]);
      const cover = imageFromCell(cells[coverIndex]);
      const title = markdownCell(cells[titleIndex]?.text ?? "");
      const description = markdownCell(descriptionIndex >= 0 ? cells[descriptionIndex]?.text ?? "" : "");
      const targetMarkdown = target
        ? `[${markdownCell(target.label)}](${target.href.replace(/\s/g, "%20")})`
        : "";
      const coverMarkdown = cover
        ? `![${markdownCell(cover.alt || title)}](${cover.src.replace(/\s/g, "%20")})`
        : "";
      return `| ${title} | ${description} | ${targetMarkdown} | ${coverMarkdown} |`;
    });

    if (rows.length === 0) return "";
    return [
      "| __MUTX_DOCS_CARD_TABLE__ | Description | Target | Cover |",
      "| --- | --- | --- | --- |",
      ...rows,
    ].join("\n");
  });
}

export function preprocessGitBookMarkdown(source: string): string {
  return preprocessGitBookCardTables(preprocessHints(source));
}
