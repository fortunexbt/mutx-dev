import { ClipboardCheck } from "lucide-react";

import { AuditPageClient } from "@/components/dashboard/AuditPageClient";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { DesktopRouteBoundary } from "@/components/desktop/DesktopRouteBoundary";

export default function DashboardAuditPage() {
  return (
    <DesktopRouteBoundary
      routeKey="audit"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="Audit evidence"
            description="Filter attributable control-plane events, inspect redacted context, and export verified evidence for one run or session."
            icon={ClipboardCheck}
            badge="governance ledger"
            stats={[
              { label: "Source", value: "/v1/audit/events", tone: "success" },
              { label: "Access", value: "Audit role", tone: "warning" },
            ]}
          />

          <AuditPageClient />
        </div>
      }
    />
  );
}
