import { History } from "lucide-react";

import { LogsPageClient } from "@/components/dashboard/LogsPageClient";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { DesktopRouteBoundary } from "@/components/desktop/DesktopRouteBoundary";

export default function DashboardHistoryPage() {
  return (
    <DesktopRouteBoundary
      routeKey="history"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="History"
            description="Review recent control-plane runs and inspect the recorded activity and trace events for each execution."
            icon={History}
            iconTone="text-slate-200 bg-white/10"
            badge="execution activity"
            stats={[
              { label: "Source", value: "Runs API" },
              { label: "Data", value: "Live", tone: "success" },
            ]}
          />

          <LogsPageClient mode="history" />
        </div>
      }
    />
  );
}
