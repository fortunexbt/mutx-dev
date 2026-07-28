export default function DashboardLoading() {
  return (
    <section
      data-boundary-surface="dashboard"
      data-boundary-kind="loading"
      className="relative isolate flex min-h-[28rem] flex-col overflow-hidden rounded-[6px] border border-[#34342e] bg-[#0d0e0c] text-[#eee9dc] shadow-[0_24px_64px_rgba(0,0,0,0.32)]"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-labelledby="dashboard-loading-title"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.025] [background-image:linear-gradient(rgba(238,233,220,0.8)_1px,transparent_1px),linear-gradient(90deg,rgba(238,233,220,0.8)_1px,transparent_1px)] [background-size:40px_40px]"
      />
      <header className="relative flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[#2b2b26] px-5 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a] sm:px-7">
        <span>Workspace / route handoff</span>
        <span className="text-[#ff8355]">REC / pending</span>
      </header>

      <div className="relative grid flex-1 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex flex-col justify-end px-5 py-10 sm:px-8 sm:py-12 lg:px-10">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.18em] text-[#ff8355]">
            Dashboard loading
          </p>
          <h1
            id="dashboard-loading-title"
            className="mt-4 max-w-3xl text-4xl font-semibold leading-none tracking-[-0.055em] sm:text-5xl"
          >
            Opening the requested dashboard surface.
          </h1>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-[#c8c0b0] sm:text-base sm:leading-7">
            MUTX is waiting for this route to become ready. Live records will appear only after the
            handoff completes.
          </p>
        </div>

        <aside className="border-t border-[#2b2b26] bg-[#0a0b09] p-6 lg:border-l lg:border-t-0 lg:p-8">
          <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8d867a]">
            Load posture
          </p>
          <div className="mt-5 flex items-center gap-3 text-sm font-medium text-[#eee9dc]">
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 rounded-full bg-[#58aaff] shadow-[0_0_18px_rgba(88,170,255,0.45)] motion-safe:animate-pulse motion-reduce:animate-none"
            />
            Waiting for route
          </div>
          <p className="mt-4 text-sm leading-6 text-[#999284]">
            Workspace records and values stay hidden while the current state is unresolved.
          </p>
        </aside>
      </div>
    </section>
  )
}
