
export async function onRequestGet({ env }) {
  try {
    const internalRequest = new Request(
      "https://status-api.internal/api/status",
      {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      }
    );

    const upstream = await env.STATUS_API.fetch(internalRequest);

    // Return only the intended status response.
    const headers = new Headers(upstream.headers);

    // This endpoint is now same-origin with the status page.
    headers.delete("Access-Control-Allow-Origin");
    headers.delete("Access-Control-Allow-Methods");
    headers.delete("Access-Control-Allow-Headers");

    return new Response(upstream.body, {
      status: upstream.status,
      headers,
    });
  } catch {
    // Do not expose internal exception details to visitors.
    return new Response(
      JSON.stringify({
        error: "Status service temporarily unavailable",
      }),
      {
        status: 502,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
        },
      }
    );
  }
}
