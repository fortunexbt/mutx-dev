'use client'

import Link from 'next/link'

export default function DashboardError({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <section
      data-boundary-surface="dashboard"
      data-boundary-kind="error"
      className="relative isolate flex min-h-[28rem] flex-col overflow-hidden rounded-[6px] border border-[#66302e] bg-[#0d0e0c] text-[#eee9dc] shadow-[0_24px_64px_rgba(0,0,0,0.32)]"
      role="alert"
      aria-labelledby="dashboard-error-title"
    >
      <header className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[#3d2927] px-5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a] sm:px-7">
        <span>Workspace / route boundary</span>
        <span className="text-[#ff9b96]">REC / interrupted</span>
      </header>

      <div className="grid flex-1 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex flex-col justify-end px-5 py-10 sm:px-8 sm:py-12 lg:px-10">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.18em] text-[#ff9b96]">
            Dashboard recovery
          </p>
          <h1
            id="dashboard-error-title"
            className="mt-4 max-w-3xl text-4xl font-semibold leading-none tracking-[-0.055em] sm:text-5xl"
          >
            This dashboard route could not finish.
          </h1>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-[#c8c0b0] sm:text-base sm:leading-7">
            The workspace shell is still available, but this surface did not load. Treat any action
            without a visible confirmation as incomplete.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={reset}
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none"
            >
              Retry route
            </button>
            <Link
              href="/dashboard"
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#11120f] px-4 text-sm font-medium text-[#eee9dc] transition-colors hover:border-[#777268] hover:bg-[#1a1b17] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none"
            >
              Dashboard home
            </Link>
          </div>
        </div>

        <aside className="border-t border-[#3d2927] bg-[#100c0b] p-6 lg:border-l lg:border-t-0 lg:p-8">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
            Scope
          </p>
          <p className="mt-5 text-xl font-semibold tracking-[-0.03em] text-[#ffb0ab]">
            Route only
          </p>
          <p className="mt-3 text-sm leading-6 text-[#aaa397]">
            Retry this surface or return to the workspace overview. No exception details are exposed
            here.
          </p>
        </aside>
      </div>
    </section>
  )
}
