"use client";

import type { ReactNode } from "react";

import { RouteHeader } from "@/components/dashboard/RouteHeader";
import { BrowserDashboardRedirect } from "@/components/desktop/BrowserDashboardRedirect";
import {
  DESKTOP_ROUTE_META,
  getDesktopRouteSurface,
  type DesktopRouteKey,
  type DesktopRouteMeta,
} from "@/components/desktop/desktopRouteConfig";
import { DesktopNativeRoutePage } from "@/components/desktop/DesktopNativeRoutePage";
import { useDesktopStatus } from "@/components/desktop/useDesktopStatus";
import { useDesktopWindow } from "@/components/desktop/useDesktopWindow";
import { DesktopSettingsWindow } from "@/components/desktop/DesktopSettingsWindow";

function AccessibleBrowserFallback({
  meta,
  desktop = false,
}: {
  meta: DesktopRouteMeta;
  desktop?: boolean;
}) {
  const titleId = `desktop-route-fallback-${meta.key}`;

  return (
    <section
      aria-labelledby={titleId}
      className="rounded-[6px] border border-[#34342e] bg-[#11120f] px-5 py-6"
    >
      <h2 id={titleId} className="font-[family:var(--font-site-display)] text-lg font-medium text-[#eee9dc]">
        {meta.title} is available in the browser dashboard
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-[#999284]">
        {desktop
          ? "This desktop build does not include a native version of this surface. Open its shared dashboard route to continue."
          : "This route could not load its dashboard surface. Use the canonical dashboard link to try again."}
      </p>
      {meta.publicHref ? (
        desktop ? (
          <button
            type="button"
            onClick={() =>
              void window.mutxDesktop?.openExternal(`https://app.mutx.dev${meta.publicHref}`)
            }
            className="mt-4 inline-flex min-h-10 items-center rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-3 py-2 text-xs font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
          >
            Open {meta.title} in browser
          </button>
        ) : (
          <a
            href={meta.publicHref}
            className="mt-4 inline-flex min-h-10 items-center rounded-[4px] border border-[#ff6a32] bg-[#ff571c] px-3 py-2 text-xs font-semibold text-[#090a08] transition-colors hover:bg-[#ff7545] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff9a72]"
          >
            Open {meta.title}
          </a>
        )
      ) : null}
    </section>
  );
}

export function DesktopRouteBoundary({
  routeKey,
  browserView,
  browserRedirectTo,
}: {
  routeKey: DesktopRouteKey;
  browserView?: ReactNode;
  browserRedirectTo?: string;
}) {
  const meta = DESKTOP_ROUTE_META[routeKey];
  const surface = getDesktopRouteSurface(routeKey);
  const { isDesktop, platformReady } = useDesktopStatus();
  const { ready } = useDesktopWindow();

  if (!platformReady) {
    return (
      <div className="space-y-4">
        <RouteHeader
          title={meta.title}
          description="Resolving the correct dashboard surface for this operator session."
          icon={meta.icon}
          iconTone={meta.iconTone}
          badge="shell bootstrap"
          stats={[
            { label: "Surface", value: "Resolving" },
            { label: "Bridge", value: "Initializing", tone: "warning" },
          ]}
        />

        <div role="status" aria-label={`Loading ${meta.title}`} className="grid gap-4 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="h-40 rounded-[6px] border border-[#2b2b26] bg-[#11120f] motion-safe:animate-pulse motion-reduce:animate-none"
            />
          ))}
        </div>
      </div>
    );
  }

  if (isDesktop && ready) {
    if (surface === "shared") {
      return <>{browserView ?? <AccessibleBrowserFallback meta={meta} desktop />}</>;
    }

    if (surface === "settings") {
      return <DesktopSettingsWindow />;
    }

    return <DesktopNativeRoutePage routeKey={routeKey} />;
  }

  if (browserRedirectTo) {
    return <BrowserDashboardRedirect href={browserRedirectTo} />;
  }

  return <>{browserView ?? <AccessibleBrowserFallback meta={meta} />}</>;
}
