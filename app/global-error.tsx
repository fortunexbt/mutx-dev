'use client'

export default function GlobalError({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0a09] text-[#f3f0e8] antialiased">
        <main
          id="main-content"
          data-boundary-surface="global"
          data-boundary-kind="error"
          className="grid min-h-screen place-items-center px-4 py-10 sm:px-6"
          role="alert"
          aria-labelledby="global-error-title"
        >
          <section className="w-full max-w-4xl overflow-hidden border border-[#48463e] bg-[#11120f] shadow-[0_28px_80px_rgba(0,0,0,0.5)]">
            <header className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[#34342e] px-5 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#999284] sm:px-7">
              <span>MUTX / application shell</span>
              <span className="text-[#ff8355]">System / interrupted</span>
            </header>

            <div className="grid min-h-[28rem] lg:grid-cols-[minmax(0,1fr)_18rem]">
              <div className="flex flex-col justify-end px-5 py-10 sm:px-8 sm:py-14 lg:px-12">
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-[#ff8355]">
                  Safe recovery screen
                </p>
                <h1
                  id="global-error-title"
                  className="mt-4 max-w-2xl text-4xl font-semibold leading-[0.98] tracking-[-0.055em] text-[#f3f0e8] sm:text-6xl"
                >
                  MUTX could not open the application shell.
                </h1>
                <p className="mt-6 max-w-2xl text-base leading-7 text-[#c8c0b0]">
                  The shared shell stopped before this surface finished rendering. This screen cannot
                  confirm whether any in-flight operation completed.
                </p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={reset}
                    className="inline-flex min-h-11 items-center justify-center border border-[#ff6a32] bg-[#ff571c] px-5 text-sm font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none"
                  >
                    Retry application
                  </button>
                  <a
                    href="/"
                    className="inline-flex min-h-11 items-center justify-center border border-[#48463e] bg-transparent px-5 text-sm font-semibold text-[#eee9dc] transition-colors hover:border-[#777268] hover:bg-[#1a1b17] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#ff9a72] motion-reduce:transition-none"
                  >
                    Return to MUTX
                  </a>
                </div>
              </div>

              <aside className="border-t border-[#34342e] bg-[#0d0e0c] p-6 lg:border-l lg:border-t-0 lg:p-8">
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#999284]">
                  Recovery posture
                </p>
                <p className="mt-5 text-xl font-semibold tracking-[-0.03em] text-[#eee9dc]">
                  No result assumed
                </p>
                <p className="mt-3 text-sm leading-6 text-[#aaa397]">
                  Retry the shell before continuing. If the interruption repeats, reopen MUTX and
                  verify the operation from its destination surface.
                </p>
              </aside>
            </div>
          </section>
        </main>
      </body>
    </html>
  )
}
