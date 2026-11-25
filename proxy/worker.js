const ORIGIN = "sheet-music-analysis-cx6osvvmya-uc.a.run.app";
const UPLOADS_PER_ADDRESS = 30;
const UPLOAD_HEADERS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
                         "Access-Control-Allow-Headers": "content-type", "Content-Type": "application/json" };
const ANSWERED_HERE = "x-answered-by";
const REFUSALS = [429, 500];

async function addressKey(request, env) {
  const day = new Date().toISOString().slice(0, 10);
  const bytes = new TextEncoder().encode(env.ADDRESS_SALT + day + (request.headers.get("cf-connecting-ip") || ""));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return day + ":" + Array.from(digest.slice(0, 12), (b) => b.toString(16).padStart(2, "0")).join("");
}

function refusedByCloudRun(response) {
  return REFUSALS.includes(response.status) && !response.headers.has(ANSWERED_HERE);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const upload = request.method === "POST" && url.pathname === "/upload";
    const key = upload ? await addressKey(request, env) : null;
    const sent = key ? await env.UPLOADS.get(key).catch(() => null) : null;
    if (Number(sent) >= UPLOADS_PER_ADDRESS) {
      return new Response(JSON.stringify({ error: "Too many files have been sent from this internet connection today. Please try again tomorrow." }),
                          { status: 429, headers: UPLOAD_HEADERS });
    }
    url.protocol = "https:";
    url.host = env.ORIGIN || ORIGIN;
    const body = ["GET", "HEAD"].includes(request.method) ? null : await request.arrayBuffer();
    const forward = () => {
      const forwarded = new Request(url, { method: request.method, headers: request.headers, body, redirect: "manual" });
      forwarded.headers.set("x-proxy-key", env.PROXY_KEY);
      return fetch(forwarded, { cache: "no-store" });
    };
    const started = Date.now();
    let response = await forward();
    if (refusedByCloudRun(response)) {
      const refused = response.status;
      const waited = Date.now() - started;
      await response.body?.cancel();
      response = await forward();
      console.log(JSON.stringify({ event: "cloud_run_refused", method: request.method, path: url.pathname, status: refused,
                                   waited_ms: waited, retry_status: response.status, rescued: !refusedByCloudRun(response) }));
    }
    if (key && response.ok) {
      await env.UPLOADS.put(key, String(Number(sent) + 1), { expirationTtl: 172800 }).catch(() => null);
    }
    return response;
  },
};
