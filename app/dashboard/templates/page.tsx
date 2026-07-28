import { LayoutGrid } from "lucide-react";

import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { TemplateCatalogPageClient } from "@/components/dashboard/TemplateCatalogPageClient";

export default function DashboardTemplatesPage() {
  return (
    <div className="space-y-4">
      <RouteHeader
        title="Templates"
        description="Browse, clone, and deploy agent templates while keeping source, validation, and deployment receipts visible."
        icon={LayoutGrid}
        badge="template catalog"
        stats={[
          { label: "Scope", value: "Templates + custom" },
          { label: "Source", value: "Live API + local catalog" },
        ]}
      />
      <TemplateCatalogPageClient />
    </div>
  );
}
