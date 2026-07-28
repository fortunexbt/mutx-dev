import Link from 'next/link'
import { ArrowLeft, BookOpen, Home } from 'lucide-react'

import { SystemState } from '@/components/site/SystemState'

export const metadata = {
  title: '404 - Page Not Found | MUTX',
  robots: { index: false, follow: false },
}

export default function NotFound() {
  return (
    <SystemState
      code="404 / NO RECORD"
      eyebrow="Route lookup complete"
      title="Nothing ran here."
      description="The requested route has no matching record. Choose a known surface and keep moving."
      detail="No agent, deployment, or workspace state was changed by this request."
      actions={(
        <>
          <Link
            href="/"
          >
            <Home className="h-4 w-4" />
            MUTX home
          </Link>
          <Link href="/docs">
            <BookOpen className="h-4 w-4" />
            Open docs
          </Link>
          <Link
            href="/dashboard"
          >
            <ArrowLeft className="h-4 w-4" />
            Dashboard
          </Link>
        </>
      )}
    />
  )
}
