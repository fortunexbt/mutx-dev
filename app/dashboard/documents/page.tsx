import { FileText } from 'lucide-react'

import { RouteHeader } from '@/components/dashboard/RouteHeader'
import { DocumentsPageClient } from '@/components/dashboard/DocumentsPageClient'
import { DesktopRouteBoundary } from '@/components/desktop/DesktopRouteBoundary'

export default function DashboardDocumentsPage() {
  return (
    <DesktopRouteBoundary
      routeKey="documents"
      browserView={
        <div className="space-y-4">
          <RouteHeader
            title="Documents"
            description="Predict-RLM-backed document workflows with managed uploads, local desktop execution, and run/trace linkage."
            icon={FileText}
            iconTone="text-amber-300 bg-amber-400/10"
            badge="document workflows"
            stats={[
              { label: 'Execution', value: 'Hybrid' },
              { label: 'Artifacts', value: 'Managed storage', tone: 'success' },
            ]}
          />

          <DocumentsPageClient />
        </div>
      }
    />
  )
}
