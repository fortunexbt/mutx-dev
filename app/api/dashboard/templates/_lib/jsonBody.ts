import { NextRequest, NextResponse } from 'next/server'

type JsonBodyResult =
  | { ok: true; body: string }
  | { ok: false; response: NextResponse<{ detail: string }> }

export async function readJsonBody(request: NextRequest): Promise<JsonBodyResult> {
  try {
    return { ok: true, body: JSON.stringify(await request.json()) }
  } catch (error) {
    const errorName =
      typeof error === 'object' && error !== null && 'name' in error
        ? String(error.name)
        : ''
    if (error instanceof SyntaxError || errorName === 'SyntaxError') {
      return {
        ok: false,
        response: NextResponse.json({ detail: 'Invalid JSON in request body' }, { status: 400 }),
      }
    }
    throw error
  }
}
