'use client'

import Link from 'next/link'

export default function ControlError({
  error: _error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      data-boundary-surface="control"
      data-boundary-kind="error"
      className="grid min-h-[100dvh] place-items-center overflow-y-auto bg-[#090a08] px-3 py-6 text-[#eee9dc] sm:px-6"
      aria-labelledby="control-error-title"
    >
      <div
        className="relative w-full max-w-5xl overflow-hidden rounded-[6px] border border-[#66302e] bg-[#11120f] shadow-[0_1px_0_rgba(255,255,255,0.025)]"
        role="alert"
      >
        <span className="absolute left-0 top-0 h-px w-28 bg-[#ff6d66]" aria-hidden="true" />
        <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-[#34342e] bg-[#0c0d0b] px-4 font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8d867a] sm:px-6">
          <span>MUTX / control demo</span>
          <span className="rounded-[3px] border border-[#66302e] bg-[#241312] px-2.5 py-1 text-[#ff9b96]">
            Demo route / interrupted
          </span>
        </header>

        <div className="grid min-h-[26rem] lg:grid-cols-[minmax(0,1fr)_19rem]">
          <div className="flex flex-col justify-end px-4 py-10 sm:px-8 lg:px-10">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#ff9b96]">
              Simulated surface recovery
            </p>
            <h1 id="control-error-title" className="mt-4 max-w-3xl text-4xl font-semibold leading-[1.02] tracking-[-0.045em] sm:text-5xl">
              The control walkthrough stopped.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-6 text-[#aaa397] sm:text-base sm:leading-7">
              This demo route did not finish rendering. Retry to reopen it; this recovery screen does
              not expose internal exception details or submit a live system action.
            </p>
            <div className="mt-7 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={reset}
                className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-4 text-sm font-semibold text-[#090a08] hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
              >
                Retry demo route
              </button>
              <Link
                href="/control"
                className="inline-flex min-h-11 items-center justify-center rounded-[4px] border border-[#48463e] bg-[#151612] px-4 text-sm font-semibold text-[#c8c0b0] hover:border-[#ff6a32] hover:text-[#eee9dc] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
              >
                Demo overview
              </Link>
            </div>
          </div>

          <aside className="border-t border-[#34342e] bg-[#0c0d0b] p-5 lg:border-l lg:border-t-0 lg:p-6">
            <p className="font-[family:var(--font-mono)] text-[11px] font-semibold uppercase tracking-[0.14em] text-[#8d867a]">
              Recovery scope
            </p>
            <p className="mt-5 text-2xl font-semibold tracking-[-0.03em] text-[#ff9b96]">Demo route only</p>
            <p className="mt-4 text-sm leading-6 text-[#999284]">
              Other MUTX product surfaces are outside this boundary. Return to the demo overview if
              the retry does not complete.
            </p>
          </aside>
        </div>
      </div>
    </main>
  )
}
