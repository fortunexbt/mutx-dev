import fs from "fs";
import path from "path";

import matter from "gray-matter";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";

// @ts-expect-error Node's direct TypeScript runner requires explicit extensions.
import { getDocsPublicationManifest, type DocsPublicationManifest, type PublishedDoc } from "../docs.ts";
// @ts-expect-error Node's direct TypeScript runner requires explicit extensions.
import { DOCS_HOME_MODEL } from "./home.ts";
// @ts-expect-error Node's direct TypeScript runner requires explicit extensions.
import { preprocessGitBookMarkdown } from "./hints.ts";
import type {
  DocsSearchDocument,
  DocsSearchEntry,
  DocsSearchIndex,
} from "./search";

function markdownToPlainText(markdown: string): string {
  return markdown
    .replace(/---[\s\S]*?---/g, " ")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/{%[\s\S]*?%}/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^>+\s?/gm, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^[-*+]\s+/gm, "")
    .replace(/^\d+\.\s+/gm, "")
    .replace(/[*_~|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function titleFromSource(content: string, fallback: string): string {
  const heading = content.match(/^#\s+(.+)$/m)?.[1];
  return (heading ?? fallback).replace(/[*_`]/g, "").trim();
}

function fallbackTitle(doc: PublishedDoc): string {
  if (doc.route === "/docs") return "MUTX Docs";
  return path.basename(doc.sourcePath, ".md")
    .replace(/^(README|index)$/i, path.basename(path.dirname(doc.sourcePath)))
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function sectionFromRoute(route: string): string {
  if (route === "/docs") return "Docs";
  if (route === "/sdk") return "SDK";
  if (route === "/support") return "Support";
  const segment = route.split("/").filter(Boolean)[1] ?? "Docs";
  return segment.replace(/-/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

interface HeadingNode {
  depth: number;
  id: string;
  text: string;
  start: number;
  end: number;
}

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
  position?: {
    start?: { offset?: number };
    end?: { offset?: number };
  };
}

function nodeText(node: HastNode): string {
  if (node.type === "text") return node.value ?? "";
  return node.children?.map(nodeText).join("") ?? "";
}

function renderedHeadingNodes(content: string): { content: string; headings: HeadingNode[] } {
  const preprocessed = preprocessGitBookMarkdown(content);
  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype, { allowDangerousHtml: false })
    .use(rehypeSlug);
  const tree = processor.runSync(processor.parse(preprocessed)) as unknown as HastNode;
  const headings: HeadingNode[] = [];

  function visit(node: HastNode) {
    const match = node.type === "element" ? node.tagName?.match(/^h([1-6])$/) : null;
    const id = node.properties?.id;
    const start = node.position?.start?.offset;
    const end = node.position?.end?.offset;

    if (match && typeof id === "string" && typeof start === "number" && typeof end === "number") {
      headings.push({
        depth: Number(match[1]),
        id,
        text: nodeText(node),
        start,
        end,
      });
    }

    node.children?.forEach(visit);
  }

  visit(tree);
  return { content: preprocessed, headings };
}

export function createDocsSearchHeadingEntries(
  content: string,
  href: string,
  section: string,
): DocsSearchEntry[] {
  const rendered = renderedHeadingNodes(content);
  const searchableHeadings = rendered.headings.filter((heading) => heading.depth <= 4);

  return searchableHeadings.map((heading, index) => {
    const nextHeading = searchableHeadings
      .slice(index + 1)
      .find((candidate) => candidate.depth <= heading.depth);

    return {
      id: `${href}#${heading.id}`,
      title: heading.text,
      section,
      content: markdownToPlainText(
        rendered.content.slice(heading.end, nextHeading?.start ?? rendered.content.length),
      ).slice(0, 500),
      href: `${href}#${heading.id}`,
      headings: [],
    };
  });
}

function documentFromPublication(doc: PublishedDoc): DocsSearchDocument {
  if (doc.route === "/docs") {
    const section = "Docs";
    const headingEntries: DocsSearchEntry[] = [
      {
        id: `/docs#${DOCS_HOME_MODEL.hero.id}`,
        title: DOCS_HOME_MODEL.hero.title,
        section,
        content: [
          DOCS_HOME_MODEL.hero.description,
          DOCS_HOME_MODEL.hero.primaryAction.label,
          DOCS_HOME_MODEL.hero.secondaryAction.label,
          ...DOCS_HOME_MODEL.featured.slice(0, 3).flatMap((item) => [
            item.title,
            item.description,
          ]),
        ].join(" "),
        href: `/docs#${DOCS_HOME_MODEL.hero.id}`,
        headings: [],
      },
      {
        id: `/docs#${DOCS_HOME_MODEL.areas.id}`,
        title: DOCS_HOME_MODEL.areas.title,
        section,
        content: DOCS_HOME_MODEL.areas.kicker,
        href: `/docs#${DOCS_HOME_MODEL.areas.id}`,
        headings: [],
      },
    ];
    const rootEntry: DocsSearchEntry = {
      id: "/docs",
      title: DOCS_HOME_MODEL.title,
      section,
      content: headingEntries.map((entry) => `${entry.title} ${entry.content}`).join(" "),
      href: "/docs",
      headings: headingEntries.map((entry) => entry.title),
    };

    return {
      title: DOCS_HOME_MODEL.title,
      href: "/docs",
      section,
      entries: [rootEntry, ...headingEntries],
    };
  }

  const source = fs.readFileSync(doc.filePath, "utf-8");
  const { data, content } = matter(source);
  const title = typeof data.title === "string" && data.title.trim()
    ? data.title.trim()
    : titleFromSource(content, fallbackTitle(doc));
  const section = sectionFromRoute(doc.route);
  const headings = createDocsSearchHeadingEntries(content, doc.route, section);
  const rootEntry: DocsSearchEntry = {
    id: doc.route,
    title,
    section,
    content: markdownToPlainText(content).slice(0, 1000),
    href: doc.route,
    headings: headings.map((entry) => entry.title),
  };

  return { title, href: doc.route, section, entries: [rootEntry, ...headings] };
}

export function createDocsSearchIndex(
  publication: DocsPublicationManifest = getDocsPublicationManifest(),
): DocsSearchIndex {
  const documents = publication.docs.map(documentFromPublication);
  return {
    version: 1,
    routes: documents.map((document) => document.href),
    documents,
  };
}

export function writeDocsSearchIndex(
  outputPath = path.join(process.cwd(), "public", "docs-search-index.json"),
): DocsSearchIndex {
  const index = createDocsSearchIndex();
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(index, null, 2)}\n`, "utf-8");
  return index;
}
