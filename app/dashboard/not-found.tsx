import Link from 'next/link'

export default function DashboardNotFound() {
  return (
    <section
      data-boundary-surface="dashboard"
      data-boundary-kind="not-found"
      className="relative isolate flex min-h-[28rem] flex-col overflow-hidden rounded-[6px] border border-[#48463e] bg-[#0d0e0c] text-[#eee9dc] shadow-[0_24px_64px_rgba(0,0,0,0.32)]"
      aria-labelledby="dashboard-not-found-title"
    >
      <header className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[#2b2b26] px-5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a] sm:px-7">
        <span>Workspace / route lookup</span>
        <span className="text-[#efb654]">REC / 404</span>
      </header>

      <div className="grid flex-1 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex flex-col justify-end px-5 py-10 sm:px-8 sm:py-12 lg:px-10">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.18em] text-[#efb654]">
            Dashboard lookup complete
          </p>
          <h1
            id="dashboard-not-found-title"
            className="mt-4 max-w-3xl text-4xl font-semibold leading-none tracking-[-0.055em] sm:text-5xl"
          >
            No dashboard record matches this route.
          </h1>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-[#c8c0b0] sm:text-base sm:leading-7">
            The address does not map to an available workspace surface. This lookup did not change
            an agent, run, or deployment.
          </p>
          <nav className="mt-7 flex flex-wrap gap-3" aria-label="Dashboard recovery">
            <Link
              href="/dashboard"
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none"
            >
              Dashboard home
            </Link>
            <Link
              href="/dashboard/runs"
              className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#11120f] px-4 text-sm font-medium text-[#eee9dc] transition-colors hover:border-[#777268] hover:bg-[#1a1b17] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none"
            >
              Open runs
            </Link>
          </nav>
        </div>

        <aside className="border-t border-[#2b2b26] bg-[#0a0b09] p-6 lg:border-l lg:border-t-0 lg:p-8">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
            Lookup result
          </p>
          <p className="mt-5 text-xl font-semibold tracking-[-0.03em] text-[#f4cc82]">
            Route unavailable
          </p>
          <p className="mt-3 text-sm leading-6 text-[#999284]">
            Use a known workspace destination to continue without leaving the dashboard shell.
          </p>
        </aside>
      </div>
    </section>
  )
}
