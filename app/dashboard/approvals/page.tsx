import { Gavel } from "lucide-react";

import { ApprovalsPageClient } from "@/components/dashboard/ApprovalsPageClient";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { DesktopRouteBoundary } from "@/components/desktop/DesktopRouteBoundary";

export default function DashboardApprovalsPage() {
  return (
    <DesktopRouteBoundary
      routeKey="approvals"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="Approval queue"
            description="Review requester intent and execution context, then resolve pending control-plane actions against the canonical approval envelope."
            icon={Gavel}
            badge="human control gate"
            stats={[
              { label: "Source", value: "/v1/approvals", tone: "success" },
              { label: "Decisions", value: "Role enforced", tone: "warning" },
            ]}
          />

          <ApprovalsPageClient />
        </div>
      }
    />
  );
}
