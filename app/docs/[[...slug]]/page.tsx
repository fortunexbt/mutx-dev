import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import fs from "fs";
import path from "path";
import matter from "gray-matter";
import Link from "next/link";
import { DocsRenderer, extractHeadings } from "@/components/site/docs/DocsRenderer";
import { TableOfContents } from "@/components/site/docs/TableOfContents";
import { SectionLanding } from "@/components/site/docs/SectionLanding";
import { PrevNextNav } from "@/components/site/docs/PrevNextNav";
import {
  DEFAULT_X_HANDLE,
  buildPageMetadata,
  getCanonicalUrl,
  getSiteUrl,
} from "@/lib/seo";
import {
  getFrontmatterDateModified,
  type DocNavItem,
  parseSummary,
  resolvePublishedDocRequest,
} from "@/lib/docs";
import { DOCS_HOME_MODEL } from "@/lib/docs/home";
import { serializeJsonLd } from "@/lib/docs/jsonLd";

export const dynamicParams = true;
export const dynamic = "force-dynamic";

function sourceSlugForDocsRenderer(filePath: string): string[] {
  const relative = path.relative(path.join(process.cwd(), "docs"), filePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return [];
  return relative.replace(/\.md$/i, "").split(path.sep);
}

function extractPrimaryHeading(source: string): string | null {
  const match = source.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : null;
}

function extractLeadParagraph(source: string): string | null {
  const paragraphs = source
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  for (const paragraph of paragraphs) {
    if (
      paragraph.startsWith("#") ||
      paragraph.startsWith(">") ||
      paragraph.startsWith("```") ||
      paragraph.startsWith("|") ||
      /^[-*]\s/.test(paragraph) ||
      /^\d+\.\s/.test(paragraph)
    ) {
      continue;
    }

    return paragraph
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/[*_]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  return null;
}

function normalizeKeywords(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((keyword): keyword is string => typeof keyword === "string");
  }

  if (typeof value === "string") {
    return value
      .split(",")
      .map((keyword) => keyword.trim())
      .filter(Boolean);
  }

  return [];
}

function getDocSeoFields(data: Record<string, unknown>, content: string) {
  const title =
    (typeof data.title === "string" && data.title.trim()) ||
    extractPrimaryHeading(content) ||
    "MUTX Docs";
  const description =
    (typeof data.description === "string" && data.description.trim()) ||
    extractLeadParagraph(content) ||
    "Documentation for MUTX operators and builders.";
  const keywords = Array.from(
    new Set([
      "mutx docs",
      "ai agent control plane",
      "agent operations",
      ...normalizeKeywords(data.keywords),
    ]),
  );

  return {
    title,
    metaTitle: title.endsWith("MUTX Docs") ? title : `${title} — MUTX Docs`,
    description,
    keywords,
  };
}

function findNavTrail(
  items: DocNavItem[],
  route: string,
  trail: DocNavItem[] = [],
): DocNavItem[] | null {
  for (const item of items) {
    const nextTrail = [...trail, item];
    if (item.route === route) {
      return nextTrail;
    }

    const childTrail = findNavTrail(item.children, route, nextTrail);
    if (childTrail) {
      return childTrail;
    }
  }

  return null;
}

function getDocBreadcrumbs(route: string, fallbackTitle: string) {
  const navTrail = findNavTrail(parseSummary(), route) ?? [];
  const breadcrumbs = [{ name: "Docs", path: "/docs" }];

  for (const item of navTrail) {
    if (item.route === "/docs") {
      continue;
    }

    if (breadcrumbs.some((breadcrumb) => breadcrumb.path === item.route)) {
      continue;
    }

    breadcrumbs.push({ name: item.title, path: item.route });
  }

  if (breadcrumbs[breadcrumbs.length - 1]?.path !== route) {
    breadcrumbs.push({ name: fallbackTitle, path: route });
  }

  return breadcrumbs;
}

function buildDocStructuredData(options: {
  title: string;
  path: string;
  description: string;
  breadcrumbs: Array<{ name: string; path: string }>;
  dateModified?: string;
}) {
  const siteUrl = getSiteUrl();

  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteUrl}/#organization`,
        name: "MUTX",
        url: siteUrl,
        sameAs: [`https://x.com/${DEFAULT_X_HANDLE.replace("@", "")}`],
      },
      {
        "@type": "SoftwareApplication",
        name: "MUTX",
        applicationCategory: "DeveloperApplication",
        description:
          "Source-available control plane for AI agent governance, deployment, and observability.",
        downloadUrl: `${siteUrl}/download`,
        offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      },
      {
        "@type": "WebPage",
        "@id": `${getCanonicalUrl(options.path)}#webpage`,
        name: options.title,
        url: getCanonicalUrl(options.path),
        description: options.description,
        isPartOf: {
          "@type": "WebSite",
          name: "MUTX Docs",
          url: getCanonicalUrl("/docs"),
        },
        ...(options.dateModified ? { dateModified: options.dateModified } : {}),
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: options.breadcrumbs.map((breadcrumb, index) => ({
          "@type": "ListItem",
          position: index + 1,
          name: breadcrumb.name,
          item: getCanonicalUrl(breadcrumb.path),
        })),
      },
    ],
  };
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}): Promise<Metadata> {
  const { slug = [] } = await params;
  const request = resolvePublishedDocRequest(slug);
  if (!request) return { title: "Not Found" };
  const filePath = request.doc.filePath;

  const source = fs.readFileSync(filePath, "utf-8");
  const { data, content } = matter(source);
  const normalizedPath = request.canonicalRoute;
  const seo = getDocSeoFields(data, content);

  return {
    title: seo.metaTitle,
    description: seo.description,
    category: "documentation",
    keywords: seo.keywords,
    ...buildPageMetadata({
      title: seo.metaTitle,
      description: seo.description,
      path: normalizedPath,
      siteName: "MUTX Docs",
      badge: "DOCS",
    }),
  };
}

const AREA_LABELS: Record<string, string> = {
  api: "API Reference",
  architecture: "Architecture",
  autonomy: "Autonomy",
  deployment: "Deployment",
  releases: "Releases",
  troubleshooting: "Troubleshooting",
};

function DocsHomePage() {
  const nav = parseSummary();
  const areas = nav.filter(
    (section) => section.children.length > 0 && section.route !== "/docs",
  );

  return (
    <div className="docs-article-layout">
      <div className="docs-article-main docs-home">
        <section className="docs-home-billboard">
          <div className="docs-home-billboard-copy">
            <p className="docs-home-kicker">{DOCS_HOME_MODEL.hero.kicker}</p>
            <h1 id={DOCS_HOME_MODEL.hero.id} className="docs-home-title">
              {DOCS_HOME_MODEL.hero.title}
            </h1>
            <p className="docs-home-sub">{DOCS_HOME_MODEL.hero.description}</p>
            <div className="docs-home-actions">
              <Link href={DOCS_HOME_MODEL.hero.primaryAction.href} className="docs-home-primary">
                {DOCS_HOME_MODEL.hero.primaryAction.label}
              </Link>
              <Link href={DOCS_HOME_MODEL.hero.secondaryAction.href} className="docs-home-secondary">
                {DOCS_HOME_MODEL.hero.secondaryAction.label}
              </Link>
            </div>
          </div>

          <div className="docs-home-ledger">
            <p className="docs-home-ledger-label">Start here</p>
            {DOCS_HOME_MODEL.featured.slice(0, 3).map((card, index) => (
              <Link key={card.href} href={card.href} className="docs-home-ledger-item">
                <span className="docs-home-ledger-index">{String(index + 1).padStart(2, "0")}</span>
                <span>
                  <span className="docs-home-ledger-title">{card.title}</span>
                  <span className="docs-home-ledger-desc">{card.description}</span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className="docs-home-areas">
          <div className="docs-home-section-heading">
            <p className="docs-home-kicker">{DOCS_HOME_MODEL.areas.kicker}</p>
            <h2 id={DOCS_HOME_MODEL.areas.id} className="docs-home-section-title">
              {DOCS_HOME_MODEL.areas.title}
            </h2>
          </div>

          <div className="docs-home-area-list">
            {areas.map((section, index) => {
              const label = AREA_LABELS[section.slug] ?? section.title;

              return (
                <div key={section.slug} className="docs-home-area-block">
                  <div className="docs-home-area-meta">
                    <span className="docs-home-area-index">{String(index + 1).padStart(2, "0")}</span>
                    <h3 className="docs-home-area-title">{label}</h3>
                  </div>
                  <SectionLanding title="" children={section.children} />
                </div>
              );
            })}
          </div>
        </section>

      </div>
    </div>
  );
}

export default async function DocPage({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const { slug = [] } = await params;
  const request = resolvePublishedDocRequest(slug);

  if (!request) {
    notFound();
  }

  if (request.shouldRedirect) {
    redirect(request.canonicalRoute);
  }

  const filePath = request.doc.filePath;
  const source = fs.readFileSync(filePath, "utf-8");
  const { data, content } = matter(source);
  const currentRoute = request.canonicalRoute;
  const seo = getDocSeoFields(data, content);
  const breadcrumbs = getDocBreadcrumbs(currentRoute, seo.title);
  const structuredData = buildDocStructuredData({
    title: seo.title,
    path: currentRoute,
    description: seo.description,
    breadcrumbs,
    dateModified: getFrontmatterDateModified(data),
  });

  if (currentRoute === "/docs") {
    return (
      <>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: serializeJsonLd(structuredData) }}
        />
        <DocsHomePage />
      </>
    );
  }

  const headings = extractHeadings(content);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(structuredData) }}
      />
      <div className="docs-article-layout">
        <div className="docs-article-main">
          <DocsRenderer source={content} currentSlug={sourceSlugForDocsRenderer(filePath)} />
          <PrevNextNav currentRoute={currentRoute} />
        </div>
        <TableOfContents sourceHeadings={headings} />
      </div>
    </>
  );
}
