import { headers } from "next/headers";

import { AuthPage } from "@/components/auth/AuthPage";
import { PicoAuthPage } from "@/components/pico/PicoAuthPage";
import {
  getDefaultRedirectPathForHost,
  isPicoHost,
} from "@/lib/auth/redirects";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{
    next?: string | string[];
    error?: string | string[];
    email?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const host = (await headers()).get("host")?.split(":")[0] ?? null;
  const nextPath = Array.isArray(params.next) ? params.next[0] : params.next;
  const error = Array.isArray(params.error) ? params.error[0] : params.error;
  const email = Array.isArray(params.email) ? params.email[0] : params.email;

  if (isPicoHost(host)) {
    return (
      <PicoAuthPage
        mode="login"
        nextPath={nextPath}
        fallbackPath={getDefaultRedirectPathForHost(host)}
        initialError={error}
        initialEmail={email}
      />
    );
  }

  return (
    <AuthPage
      mode="login"
      nextPath={nextPath}
      fallbackPath={getDefaultRedirectPathForHost(host)}
      initialError={error}
      initialEmail={email}
    />
  );
}
