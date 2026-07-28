export default function ControlLoading() {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      data-boundary-surface="control"
      data-boundary-kind="loading"
      className="grid min-h-[100dvh] place-items-center overflow-y-auto bg-[#090a08] px-3 py-6 text-[#eee9dc] sm:px-6"
      aria-labelledby="control-loading-title"
    >
      <div
        className="relative w-full max-w-5xl overflow-hidden rounded-[6px] border border-[#34342e] bg-[#11120f] shadow-[0_1px_0_rgba(255,255,255,0.025)]"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <span className="absolute left-0 top-0 h-px w-28 bg-[#ff571c]" aria-hidden="true" />
        <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-[#2b2b26] bg-[#0c0d0b] px-4 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8d867a] sm:px-6">
          <span>MUTX / control demo</span>
          <span className="rounded-[3px] border border-[#5a3a2d] bg-[#21140f] px-2.5 py-1 text-[#ff9a72]">
            Demo route / pending
          </span>
        </header>

        <div className="grid min-h-[26rem] lg:grid-cols-[minmax(0,1fr)_19rem]">
          <div className="flex flex-col justify-end px-4 py-10 sm:px-8 lg:px-10">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#ff8355]">
              Simulated surface handoff
            </p>
            <h1 id="control-loading-title" className="mt-4 max-w-3xl text-4xl font-semibold leading-[1.02] tracking-[-0.045em] sm:text-5xl">
              Preparing the control walkthrough.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-6 text-[#aaa397] sm:text-base sm:leading-7">
              MUTX is resolving the requested demo route. No live system is connected, and no sample
              values are shown during this handoff.
            </p>
          </div>

          <aside className="border-t border-[#2b2b26] bg-[#0c0d0b] p-5 lg:border-l lg:border-t-0 lg:p-6">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8d867a]">
              Boundary status
            </p>
            <div className="mt-5 flex items-center gap-3 text-sm font-semibold text-[#eee9dc]">
                <span
                  aria-hidden="true"
                  className="h-2 w-2 rounded-full bg-[#ff571c] motion-safe:animate-pulse motion-reduce:animate-none"
                />
              Route pending
            </div>
            <p className="mt-4 text-sm leading-6 text-[#999284]">
              The walkthrough will identify itself as simulated when the requested surface is ready.
            </p>
          </aside>
        </div>
      </div>
    </main>
  );
}
