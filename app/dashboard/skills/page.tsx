'use client'

import { BrainCircuit } from 'lucide-react'

import { RouteHeader } from '@/components/dashboard/RouteHeader'
import { SkillsPageClient } from '@/components/dashboard/SkillsPageClient'
import { DesktopRouteBoundary } from '@/components/desktop/DesktopRouteBoundary'

export default function DashboardSkillsPage() {
  return (
    <DesktopRouteBoundary
      routeKey='skills'
      browserView={
        <div className='space-y-4'>
          <RouteHeader
            title='Skills'
            description='Pinned Orchestra Research imports, curated bundles, and runtime-ready skill inventory for live assistants.'
            icon={BrainCircuit}
            iconTone='text-cyan-300 bg-cyan-400/10'
            badge='skillpack control'
            hint={{
              tone: 'boundary',
              detail:
                'Skill configuration persists through the control plane. Runtime-ready status requires an enabled assistant provider to report reconciliation evidence.',
            }}
            stats={[
              { label: 'Catalog', value: 'ClawHub + Orchestra' },
              { label: 'Mode', value: 'Live install', tone: 'success' },
            ]}
          />

          <SkillsPageClient />
        </div>
      }
    />
  )
}
