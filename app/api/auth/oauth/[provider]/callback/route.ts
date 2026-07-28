import { NextRequest, NextResponse } from "next/server";

import {
  applyAuthCookies,
  getApiBaseUrl,
  getCookieDomain,
  shouldUseSecureCookies,
} from "@/app/api/_lib/controlPlane";
import {
  getDefaultRedirectPathForHost,
  resolveRedirectPath,
} from "@/lib/auth/redirects";
import { getAppUrl, getPicoUrl, getSiteUrl } from "@/lib/seo";

const OAUTH_COOKIE_PREFIX = "mutx_oauth";
const SUPPORTED_PROVIDERS = new Set(["google", "github", "discord", "apple"]);

function resolveProvider(value: string) {
  return SUPPORTED_PROVIDERS.has(value) ? value : null;
}

function resolveIntent(value: string | null) {
  return value === "register" ? "register" : "login";
}

function clearOAuthCookies(response: NextResponse, request: NextRequest) {
  const secure = shouldUseSecureCookies(request);
  const domain = getCookieDomain(request);

  for (const suffix of ["state", "next", "intent"]) {
    response.cookies.set(`${OAUTH_COOKIE_PREFIX}_${suffix}`, "", {
      httpOnly: true,
      sameSite: "none",
      secure,
      domain,
      path: "/",
      maxAge: 0,
    });
  }
}

function normalizeCanonicalOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      (url.pathname !== "/" && url.pathname !== "") ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    return url.origin;
  } catch {
    return null;
  }
}

function getCanonicalRequestOrigin(request: NextRequest): string {
  const canonicalOrigins = [getSiteUrl(), getAppUrl(), getPicoUrl()]
    .map(normalizeCanonicalOrigin)
    .filter((origin): origin is string => Boolean(origin));

  if (process.env.NODE_ENV !== "production") {
    canonicalOrigins.push(
      "http://localhost:3000",
      "http://app.localhost:3000",
      "http://pico.localhost:3000",
    );
  }

  const requestOrigin = normalizeCanonicalOrigin(request.nextUrl.origin);
  if (requestOrigin && canonicalOrigins.includes(requestOrigin)) {
    return requestOrigin;
  }

  return normalizeCanonicalOrigin(getAppUrl()) ?? "https://app.mutx.dev";
}

function buildAuthRedirect(
  origin: string,
  intent: string,
  nextPath: string,
  error: string,
) {
  const url = new URL(`/${intent}`, origin);
  url.searchParams.set("next", nextPath);
  url.searchParams.set("error", error);
  return url;
}

function resolveCallbackRedirectPath(
  value: string | null,
  origin: string,
  fallback: string,
): string {
  const path = resolveRedirectPath(value, fallback);
  try {
    const resolved = new URL(path, origin);
    if (resolved.origin !== origin) {
      return fallback;
    }
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider: rawProvider } = await context.params;
  const provider = resolveProvider(rawProvider);
  const publicOrigin = getCanonicalRequestOrigin(request);
  const intent = resolveIntent(
    request.cookies.get(`${OAUTH_COOKIE_PREFIX}_intent`)?.value ?? null,
  );
  const fallbackPath = getDefaultRedirectPathForHost(
    new URL(publicOrigin).hostname,
  );
  const nextPath = resolveCallbackRedirectPath(
    request.cookies.get(`${OAUTH_COOKIE_PREFIX}_next`)?.value ??
      request.nextUrl.searchParams.get("next"),
    publicOrigin,
    fallbackPath,
  );

  const fail = (message: string) => {
    const response = NextResponse.redirect(
      buildAuthRedirect(publicOrigin, intent, nextPath, message),
    );
    clearOAuthCookies(response, request);
    return response;
  };

  if (!provider) {
    return fail("OAuth sign-in is unavailable.");
  }

  const providerError =
    request.nextUrl.searchParams.get("error_description") ??
    request.nextUrl.searchParams.get("error");
  if (providerError) {
    return fail("OAuth sign-in was not completed. Try again.");
  }

  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const storedState = request.cookies.get(
    `${OAUTH_COOKIE_PREFIX}_state`,
  )?.value;

  if (!code || !state || !storedState || state !== storedState) {
    return fail("OAuth session expired. Start sign-in again.");
  }

  const redirectUri = `${publicOrigin}/api/auth/oauth/${provider}/callback`;
  const response = await fetch(
    `${getApiBaseUrl()}/v1/auth/oauth/${provider}/exchange`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        redirect_uri: redirectUri,
        state,
      }),
      cache: "no-store",
    },
  );

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    return fail("OAuth sign-in failed. Try again or use email.");
  }

  const successResponse = NextResponse.redirect(new URL(nextPath, publicOrigin));
  applyAuthCookies(successResponse, request, payload);
  clearOAuthCookies(successResponse, request);
  return successResponse;
}

/**
 * Apple Sign In uses `response_mode=form_post`, which means the callback
 * arrives as a POST with the `code` and `state` in the request body
 * (application/x-www-form-urlencoded) instead of query parameters.
 *
 * This handler extracts those values from the form body and performs the
 * same exchange flow as the GET handler above.
 */
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider: rawProvider } = await context.params;
  const provider = resolveProvider(rawProvider);
  const publicOrigin = getCanonicalRequestOrigin(request);
  const intent = resolveIntent(
    request.cookies.get(`${OAUTH_COOKIE_PREFIX}_intent`)?.value ?? null,
  );
  const fallbackPath = getDefaultRedirectPathForHost(
    new URL(publicOrigin).hostname,
  );
  const nextPath = resolveCallbackRedirectPath(
    request.cookies.get(`${OAUTH_COOKIE_PREFIX}_next`)?.value ?? null,
    publicOrigin,
    fallbackPath,
  );

  const fail = (message: string) => {
    const response = NextResponse.redirect(
      buildAuthRedirect(publicOrigin, intent, nextPath, message),
    );
    clearOAuthCookies(response, request);
    return response;
  };

  if (!provider) {
    return fail("OAuth sign-in is unavailable.");
  }

  // Parse form body — Apple sends code + state as form-encoded POST
  const formData = await request.formData();
  const providerError =
    formData.get("error_description")?.toString() ??
    formData.get("error")?.toString();
  if (providerError) {
    return fail("OAuth sign-in was not completed. Try again.");
  }

  const code = formData.get("code")?.toString();
  const state = formData.get("state")?.toString();
  const storedState = request.cookies.get(
    `${OAUTH_COOKIE_PREFIX}_state`,
  )?.value;

  if (!code || !state || !storedState || state !== storedState) {
    return fail("OAuth session expired. Start sign-in again.");
  }

  const redirectUri = `${publicOrigin}/api/auth/oauth/${provider}/callback`;
  const response = await fetch(
    `${getApiBaseUrl()}/v1/auth/oauth/${provider}/exchange`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        redirect_uri: redirectUri,
        state,
      }),
      cache: "no-store",
    },
  );

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    return fail("OAuth sign-in failed. Try again or use email.");
  }

  const successResponse = NextResponse.redirect(new URL(nextPath, publicOrigin));
  applyAuthCookies(successResponse, request, payload);
  clearOAuthCookies(successResponse, request);
  return successResponse;
}
