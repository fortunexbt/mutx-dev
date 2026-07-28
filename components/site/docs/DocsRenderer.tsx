import { unified, type Plugin } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkRehype from "remark-rehype";
import rehypeHighlight from "rehype-highlight";
import rehypeSlug from "rehype-slug";
import rehypeAutolinkHeadings from "rehype-autolink-headings";
import rehypeStringify from "rehype-stringify";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { getDocsPublicationManifest, type DocsPublicationManifest } from "@/lib/docs";
import { preprocessGitBookMarkdown } from "@/lib/docs/hints";
import type { Blockquote, Root, Text } from "mdast";
import { visit } from "unist-util-visit";
import { resolveDocAssetHref, resolveDocHref } from "@/lib/docsLinks";

export interface Heading {
  id: string;
  text: string;
  level: number;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\p{Mark}_ -]/gu, "")
    .replace(/ /g, "-")
    .trim();
}

export function extractDocumentTitle(source: string, fallback: string): string {
  const titleLine = source.split("\n").find((line) => /^#\s+/.test(line));
  if (!titleLine) return fallback;

  const title = titleLine
    .replace(/^#\s+/, "")
    .replace(/[*_`]/g, "")
    .trim();
  return title || fallback;
}

function remarkResolveDocLinks(
  currentSlug: string[],
  publication: DocsPublicationManifest,
): Plugin<[], Root> {
  return () => (tree: Root) => {
    visit(tree, "link", (node) => {
      const href = node.url || "";
      const resolved = resolveDocHref(href, currentSlug, publication);
      if (resolved === href) return;
      const cleanHref = href.split("#", 1)[0].replace(/\.md$/i, "");
      const filename = cleanHref;
      const firstChild = node.children?.[0];
      const linkText = (firstChild && "value" in firstChild ? firstChild.value : "") || "";
      if (linkText === href || linkText === filename) {
        const displayText = filename
          .replace(/[-_]/g, " ")
          .replace(/\b\w/g, (c: string) => c.toUpperCase());
        node.children = [{ type: "text", value: displayText }];
      }

      node.url = resolved;
    });

    visit(tree, "image", (node) => {
      node.url = resolveDocAssetHref(node.url || "", currentSlug);
    });
  };
}

type TableNode = {
  type: "table";
  data?: { hProperties?: Record<string, unknown> };
  children: Array<{
    children: Array<{ children: Array<{ type: string; value?: string }> }>;
  }>;
};

const remarkDecorateGitBookBlocks: Plugin<[], Root> = () => (tree) => {
  visit(tree, "table", (node) => {
    const table = node as unknown as TableNode;
    const marker = table.children[0]?.children[0]?.children[0];
    if (marker?.type !== "text" || marker.value !== "__MUTX_DOCS_CARD_TABLE__") return;

    marker.value = "Title";
    table.data = table.data ?? {};
    table.data.hProperties = {
      ...(table.data.hProperties ?? {}),
      "data-view": "cards",
    };
  });

  visit(tree, "blockquote", (node) => {
    const blockquote = node as Blockquote;
    const firstParagraph = blockquote.children[0];
    if (firstParagraph?.type !== "paragraph") return;
    const firstText = firstParagraph.children[0] as Text | undefined;
    if (firstText?.type !== "text") return;

    const match = firstText.value.match(/^\[!(NOTE|INFO|TIP|WARNING|CAUTION|DANGER)\](?:\s*)/i);
    if (!match) return;

    const rawType = match[1].toUpperCase();
    const type = rawType === "TIP"
      ? "tip"
      : rawType === "WARNING" || rawType === "CAUTION"
        ? "warning"
        : rawType === "DANGER"
          ? "danger"
          : "note";
    const label = type === "note" ? "Note" : `${type[0].toUpperCase()}${type.slice(1)}`;
    firstText.value = firstText.value.slice(match[0].length);
    blockquote.data = {
      ...(blockquote.data ?? {}),
      hProperties: {
        className: ["docs-callout"],
        dataType: type,
        role: "note",
        ariaLabel: label,
      },
    };
  });
};

const remarkOmitFirstH1: Plugin<[], Root> = () => (tree) => {
  const firstH1Index = tree.children.findIndex(
    (node) => node.type === "heading" && node.depth === 1,
  );
  if (firstH1Index >= 0) tree.children.splice(firstH1Index, 1);
};

export function extractHeadings(source: string): Heading[] {
  const headings: Heading[] = [];
  const slugCounts = new Map<string, number>();
  const lines = source.split("\n");
  for (const line of lines) {
    const m = line.match(/^(#{2,4})\s+(.+)/);
    if (m) {
      const text = m[2].replace(/[*_`]/g, "").trim();
      // Match rehype-slug's GitHub-style duplicate suffixes so TOC links
      // remain deterministic even when a document repeats a heading.
      const baseId = slugify(text);
      const count = slugCounts.get(baseId) ?? 0;
      slugCounts.set(baseId, count + 1);
      headings.push({
        id: count === 0 ? baseId : `${baseId}-${count}`,
        text,
        level: m[1].length,
      });
    }
  }
  return headings;
}

const docsSchema = {
  ...defaultSchema,
  clobberPrefix: "",
  tagNames: [
    ...(defaultSchema.tagNames || []),
    "article",
    "section",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "blockquote",
    "code",
    "pre",
  ],
  attributes: {
    ...defaultSchema.attributes,
    a: [
      ...(defaultSchema.attributes?.a || []),
      "href",
      "title",
      "target",
      "rel",
      "className",
      "aria-label",
      "ariaLabel",
    ],
    img: [...(defaultSchema.attributes?.img || []), "src", "alt", "title", "className"],
    table: [...(defaultSchema.attributes?.table || []), "data-view", "className"],
    blockquote: [
      ...(defaultSchema.attributes?.blockquote || []),
      "data-type",
      "dataType",
      "className",
      "role",
      "aria-label",
      "ariaLabel",
    ],
    code: [...(defaultSchema.attributes?.code || []), "className"],
    th: [...(defaultSchema.attributes?.th || []), "align"],
    td: [...(defaultSchema.attributes?.td || []), "align"],
    h2: [...(defaultSchema.attributes?.h2 || []), "id"],
    h3: [...(defaultSchema.attributes?.h3 || []), "id"],
    h4: [...(defaultSchema.attributes?.h4 || []), "id"],
    span: [...(defaultSchema.attributes?.span || []), "className"],
  },
};

interface DocsRendererProps {
  source: string;
  currentSlug?: string[];
  omitFirstH1?: boolean;
}

export async function renderDocsMarkdownToHtml({
  source,
  currentSlug = [],
  omitFirstH1 = false,
}: DocsRendererProps): Promise<string> {
  const preprocessed = preprocessGitBookMarkdown(source);
  const publication = getDocsPublicationManifest();

  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkResolveDocLinks(currentSlug, publication))
    .use(remarkDecorateGitBookBlocks);

  if (omitFirstH1) processor.use(remarkOmitFirstH1);

  const result = await processor
    .use(remarkRehype, { allowDangerousHtml: false })
    .use(rehypeSlug)
    .use(rehypeAutolinkHeadings, {
      behavior: "append",
      properties: {
        className: ["heading-anchor"],
        ariaLabel: "Link to this section",
      },
      content: {
        type: "element",
        tagName: "span",
        properties: {},
        children: [{ type: "text", value: "#" }],
      },
    })
    .use(rehypeHighlight, { detect: true })
    .use(rehypeSanitize, docsSchema)
    .use(rehypeStringify)
    .process(preprocessed);

  return result.toString();
}

export async function DocsRenderer(props: DocsRendererProps) {
  const html = await renderDocsMarkdownToHtml(props);

  const { DocsRendererClient } = await import("./DocsRendererClient");
  return <DocsRendererClient html={html} />;
}
