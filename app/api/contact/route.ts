import { type NextResponse } from 'next/server'

import { capturePublicLead } from '@/app/api/_lib/leadCapture'

export const dynamic = 'force-dynamic'

export async function POST(request: Request): Promise<NextResponse> {
  return capturePublicLead(request, 'pico-landing')
}
