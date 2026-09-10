const API_URL = process.env.ASTRA_API_URL?.replace(/\/$/, "");
const API_KEY = process.env.ASTRA_API_KEY ?? process.env.APP_API_KEY;

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  if (!API_URL || !API_KEY) {
    return Response.json(
      { detail: "The Astra backend proxy is not configured." },
      { status: 503 },
    );
  }

  const { path } = await context.params;
  const incoming = new URL(request.url);
  const upstreamUrl = `${API_URL}/${path.map(encodeURIComponent).join("/")}${incoming.search}`;
  const headers = new Headers({ Authorization: `Bearer ${API_KEY}` });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      signal: request.signal,
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "cache-control", "x-accel-buffering"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "The Astra backend is unavailable." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
