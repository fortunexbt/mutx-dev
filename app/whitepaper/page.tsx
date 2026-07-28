import fs from "fs";
import path from "path";
import type { Metadata } from "next";
import matter from "gray-matter";
import { DocsLayout } from "@/components/site/docs/DocsLayout";
import { DocsRenderer, extractDocumentTitle } from "@/components/site/docs/DocsRenderer";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";


export async function generateMetadata(): Promise<Metadata> {
  const source = fs.readFileSync(path.join(process.cwd(), "docs/whitepaper.md"), "utf-8");
  const { data } = matter(source);
  const title = `${data.title || "Whitepaper"} — MUTX`;
  const description = data.description as string;

  return {
    title,
    description,
    ...buildPageMetadata({ title, description, path: "/whitepaper" }),
  };
}

export default async function WhitepaperPage() {
  const source = fs.readFileSync(path.join(process.cwd(), "docs/whitepaper.md"), "utf-8");
  const { data, content } = matter(source);
  const documentTitle = (data.title as string) || extractDocumentTitle(content, "Whitepaper");

  return (
    <DocsLayout nav={[]} title={documentTitle}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(buildWebPageStructuredData({ name: `${data.title || "Whitepaper"} | MUTX`, path: "/whitepaper", description: (data.description as string) || "" })) }}
      />
      <DocsRenderer source={content} currentSlug={["whitepaper"]} omitFirstH1 />
    </DocsLayout>
  );
}
