const CACHE_TTL_SECONDS = 15;
const MAX_BODY_BYTES = 32 * 1024;

// This is a public, read-only status endpoint, so it may be called by the
// Minecraft page hosted on a different domain. CORS does not replace rate
// limiting or backend hardening; it only allows browser JavaScript to read it.
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Accept",
  "Access-Control-Max-Age": "86400",
};


function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validCheck(value) {
  if (!isPlainObject(value) || typeof value.online !== "boolean") return false;
  if (value.ping !== undefined && value.ping !== null &&
      (!Number.isFinite(value.ping) || value.ping < 0 || value.ping > 120000)) return false;
  if (value.http_status !== undefined &&
      (!Number.isInteger(value.http_status) || value.http_status < 100 || value.http_status > 599)) return false;
  if (value.players !== undefined &&
      (!Number.isInteger(value.players) || value.players < 0 || value.players > 10000000)) return false;
  if (value.max_players !== undefined &&
      (!Number.isInteger(value.max_players) || value.max_players < 0 || value.max_players > 10000000)) return false;
  for (const key of ["version", "motd", "error", "provider"]) {
    if (value[key] !== undefined && value[key] !== null &&
        (typeof value[key] !== "string" || value[key].length > 500)) return false;
  }
  return true;
}

function validStatusPayload(payload) {
  if (!isPlainObject(payload)) return false;
  const required = ["java", "bedrock", "dynmap", "main_site", "minecraft_site", "status_page", "checked"];
  if (!required.every((key) => Object.prototype.hasOwnProperty.call(payload, key))) return false;
  if (!validCheck(payload.java) || !validCheck(payload.bedrock) ||
      !validCheck(payload.dynmap) || !validCheck(payload.main_site) ||
      !validCheck(payload.minecraft_site) || !validCheck(payload.status_page)) return false;
  if (!Number.isSafeInteger(payload.checked) || payload.checked < 0) return false;
  if (payload.dynmap.configured !== undefined && typeof payload.dynmap.configured !== "boolean") return false;
  if (payload.bedrock.provider_checks !== undefined) {
    if (!Array.isArray(payload.bedrock.provider_checks) || payload.bedrock.provider_checks.length > 4) return false;
    if (!payload.bedrock.provider_checks.every((item) =>
      isPlainObject(item) &&
      typeof item.provider === "string" && item.provider.length <= 80 &&
      typeof item.online === "boolean" &&
      (item.error === null || item.error === undefined ||
        (typeof item.error === "string" && item.error.length <= 200))
    )) return false;
  }
  return true;
}

function errorResponse(status, message, extraHeaders = {}) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "X-Robots-Tag": "noindex, nofollow",
      "Strict-Transport-Security": "max-age=31536000",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
      ...extraHeaders,
    },
  });
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // Validate the endpoint before handling preflight so this function only
  // responds on its intended path and does not accept query-string variants.
  if (url.pathname !== "/api/status" || url.search) {
    return errorResponse(404, "Not found");
  }

  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        ...CORS_HEADERS,
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Strict-Transport-Security": "max-age=31536000",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
      },
    });
  }

  // This route is intentionally GET-only and does not accept query parameters.
  if (request.method !== "GET") {
    return errorResponse(405, "Method not allowed", { Allow: "GET, OPTIONS" });
  }
  if (!env.STATUS_API) {
    return errorResponse(503, "Status service temporarily unavailable");
  }

  const cache = caches.default;
  // A fixed key prevents query parameters from creating unlimited cache entries.
  const cacheKey = new Request(`${url.origin}/api/status`, { method: "GET" });

  try {
    const cached = await cache.match(cacheKey);
    if (cached) return cached;
  } catch {
    // If cache lookup fails, try the backend rather than failing the dashboard.
  }

  try {
    // Calls the backend through the internal Service Binding, not a public URL.
    const internalRequest = new Request("https://status-api.internal/api/status", {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(8_000),
    });

    const upstream = await env.STATUS_API.fetch(internalRequest);
    if (!upstream.ok) {
      return errorResponse(502, "Status service temporarily unavailable");
    }
    const contentType = (upstream.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("application/json")) {
      return errorResponse(502, "Status service returned an invalid response");
    }

    const declaredLength = Number(upstream.headers.get("content-length") || 0);
    if (declaredLength > MAX_BODY_BYTES) {
      return errorResponse(502, "Status service returned an invalid response");
    }

    const body = await upstream.text();
    if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
      return errorResponse(502, "Status service returned an invalid response");
    }
    let payload;
    try {
      payload = JSON.parse(body);
    } catch {
      return errorResponse(502, "Status service returned an invalid response");
    }
    // The backend contract is a JSON object with these known status groups.
    // Validate shape before forwarding untrusted upstream content to browsers.
    if (!validStatusPayload(payload)) {
      return errorResponse(502, "Status service returned an invalid response");
    }

    const response = new Response(body, {
      status: 200,
      headers: {
        ...CORS_HEADERS,
        "Content-Type": "application/json; charset=utf-8",
        // Browser revalidates; Cloudflare's Cache API keeps a copy for 15 seconds.
        "Cache-Control": `public, max-age=0, s-maxage=${CACHE_TTL_SECONDS}`,
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow",
        "Strict-Transport-Security": "max-age=31536000",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
      },
    });

    try {
      context.waitUntil(cache.put(cacheKey, response.clone()).catch(() => {}));
    } catch {
      // Cache storage is an optimization; a successful response can still be returned.
    }
    return response;
  } catch {
    return errorResponse(502, "Status service temporarily unavailable");
  }
}
