const CANONICAL_WEBHOOK_DOCS_ROUTE = "/docs/reference/webhooks";

function permanentRedirectResponse(): Response {
  return new Response(null, {
    status: 308,
    headers: {
      Location: CANONICAL_WEBHOOK_DOCS_ROUTE,
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}

export function GET(): Response {
  return permanentRedirectResponse();
}

export function HEAD(): Response {
  return permanentRedirectResponse();
}
