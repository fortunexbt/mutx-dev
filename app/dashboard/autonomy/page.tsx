import { Bot } from "lucide-react";

import { AutonomyPageClient } from "@/components/dashboard/AutonomyPageClient";
import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { DesktopRouteBoundary } from "@/components/desktop/DesktopRouteBoundary";

export default function DashboardAutonomyPage() {
  return (
    <DesktopRouteBoundary
      routeKey="autonomy"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="Autonomy"
            description="Local view for the live autonomy daemon, queue depth, active runners, and recent reports."
            icon={Bot}
            iconTone="text-fuchsia-300 bg-fuchsia-400/10"
            badge="local autonomy surface"
            hint={{
              tone: 'boundary',
              detail:
                'Autonomy is machine-host scoped. A host without the local daemon and repository queue configured reports the feed as unavailable.',
            }}
            stats={[
              { label: "Source", value: ".autonomy + queue", tone: "success" },
              { label: "Scope", value: "Daemon + lanes + reports" },
            ]}
          />

          <AutonomyPageClient />
        </div>
      }
    />
  );
}
