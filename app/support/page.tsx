import fs from "fs";
import path from "path";
import type { Metadata } from "next";
import matter from "gray-matter";
import { DocsLayout } from "@/components/site/docs/DocsLayout";
import { DocsRenderer } from "@/components/site/docs/DocsRenderer";
import { serializeJsonLd } from "@/lib/docs/jsonLd";
import { buildPageMetadata, buildWebPageStructuredData } from "@/lib/seo";

export async function generateMetadata(): Promise<Metadata> {
  const source = fs.readFileSync(path.join(process.cwd(), "support.md"), "utf-8");
  const { data } = matter(source);
  const title = `${data.title || "Support"} — MUTX`;
  const description = data.description as string;

  return {
    title,
    description,
    ...buildPageMetadata({ title, description, path: "/support" }),
  };
}

export default async function SupportPage() {
  const source = fs.readFileSync(path.join(process.cwd(), "support.md"), "utf-8");
  const { data, content } = matter(source);
  const structuredData = buildWebPageStructuredData({
    name: `${data.title || "Support"} | MUTX`,
    path: "/support",
    description: (data.description as string) || "",
  });

  return (
    <DocsLayout nav={[]} title={(data.title as string) || "Support"}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(structuredData) }}
      />
      <DocsRenderer source={content} currentSlug={["support"]} />
    </DocsLayout>
  );
}
