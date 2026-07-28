import fs from "fs";
import path from "path";
import type { Metadata } from "next";
import matter from "gray-matter";
import { DocsLayout } from "@/components/site/docs/DocsLayout";
import { DocsRenderer, extractDocumentTitle } from "@/components/site/docs/DocsRenderer";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";


export async function generateMetadata(): Promise<Metadata> {
  const source = fs.readFileSync(path.join(process.cwd(), "docs/roadmap.md"), "utf-8");
  const { data } = matter(source);
  const title = `${data.title || "Roadmap"} — MUTX`;
  const description = data.description as string;

  return {
    title,
    description,
    ...buildPageMetadata({ title, description, path: "/roadmap" }),
  };
}

export default async function RoadmapPage() {
  const source = fs.readFileSync(path.join(process.cwd(), "docs/roadmap.md"), "utf-8");
  const { data, content } = matter(source);
  const documentTitle = (data.title as string) || extractDocumentTitle(content, "Roadmap");

  return (
    <DocsLayout nav={[]} title={documentTitle}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(buildWebPageStructuredData({ name: `${data.title || "Roadmap"} | MUTX`, path: "/roadmap", description: (data.description as string) || "" })) }}
      />
      <DocsRenderer source={content} currentSlug={["roadmap"]} omitFirstH1 />
    </DocsLayout>
  );
}
