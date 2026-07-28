import { TerminalSquare } from "lucide-react";

import { LogsPageClient } from "@/components/dashboard/LogsPageClient";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { DesktopRouteBoundary } from "@/components/desktop/DesktopRouteBoundary";

export default function DashboardLogsPage() {
  return (
    <DesktopRouteBoundary
      routeKey="logs"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="Logs"
            description="Inspect the trace events, messages, and payloads recorded for recent control-plane runs."
            icon={TerminalSquare}
            iconTone="text-slate-200 bg-white/10"
            badge="run traces"
            stats={[
              { label: "Source", value: "Runs API" },
              { label: "Data", value: "Live", tone: "success" },
            ]}
          />

          <LogsPageClient />
        </div>
      }
    />
  );
}
