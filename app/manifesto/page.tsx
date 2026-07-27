import fs from "fs";
import path from "path";
import type { Metadata } from "next";
import matter from "gray-matter";
import { DocsLayout } from "@/components/site/docs/DocsLayout";
import { DocsRenderer } from "@/components/site/docs/DocsRenderer";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";

export async function generateMetadata(): Promise<Metadata> {
  const source = fs.readFileSync(path.join(process.cwd(), "docs/manifesto.md"), "utf-8");
  const { data } = matter(source);
  const title = `${data.title || "Manifesto"} — MUTX`;
  const description = data.description as string;

  return {
    title,
    description,
    ...buildPageMetadata({ title, description, path: "/manifesto" }),
  };
}

export default async function ManifestoPage() {
  const source = fs.readFileSync(path.join(process.cwd(), "docs/manifesto.md"), "utf-8");
  const { data, content } = matter(source);

  const structuredData = buildWebPageStructuredData({
    name: `${data.title || "Manifesto"} | MUTX`,
    path: "/manifesto",
    description: (data.description as string) || "",
  });

  return (
    <DocsLayout nav={[]} title={(data.title as string) || "Manifesto"}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <DocsRenderer source={content} currentSlug={["manifesto"]} />
    </DocsLayout>
  );
}
