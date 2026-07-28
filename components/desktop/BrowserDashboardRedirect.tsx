"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function BrowserDashboardRedirect({
  href,
}: {
  href: string;
}) {
  const router = useRouter();

  useEffect(() => {
    router.replace(href);
  }, [href, router]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-[6px] border border-[#34342e] bg-[#11120f] px-4 py-5 text-sm text-[#999284]"
    >
      Redirecting to <a href={href} className="text-[#ff8355] underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff7847]">{href}</a>…
    </div>
  );
}
