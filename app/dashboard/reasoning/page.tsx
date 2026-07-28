import { Brain } from "lucide-react";

import { ReasoningPageClient } from "@/components/dashboard/ReasoningPageClient";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { DesktopRouteBoundary } from "@/components/desktop/DesktopRouteBoundary";

export default function DashboardReasoningPage() {
  return (
    <DesktopRouteBoundary
      routeKey="reasoning"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="Reasoning"
            description="Autoreason refinement jobs with blind judging, persisted artifacts, and direct run/trace linkage."
            icon={Brain}
            iconTone="text-violet-300 bg-violet-400/10"
            badge="autoreason v1"
            stats={[
              { label: "Loop", value: "A/B/AB" },
              { label: "Judging", value: "Blind panel", tone: "success" },
            ]}
          />

          <ReasoningPageClient />
        </div>
      }
    />
  );
}
