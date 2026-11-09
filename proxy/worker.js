const ORIGIN = "sheet-music-analysis-cx6osvvmya-uc.a.run.app";
const UPLOADS_PER_ADDRESS = 30;
const UPLOAD_HEADERS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
                         "Access-Control-Allow-Headers": "content-type", "Content-Type": "application/json" };

async function addressKey(request) {
  const day = new Date().toISOString().slice(0, 10);
  const bytes = new TextEncoder().encode(day + (request.headers.get("cf-connecting-ip") || ""));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return day + ":" + Array.from(digest.slice(0, 12), (b) => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const upload = request.method === "POST" && url.pathname === "/upload";
    const key = upload ? await addressKey(request) : null;
    if (key && Number(await env.UPLOADS.get(key)) >= UPLOADS_PER_ADDRESS) {
      return new Response(JSON.stringify({ error: "Too many files have been sent from this internet connection today. Please try again tomorrow." }),
                          { status: 429, headers: UPLOAD_HEADERS });
    }
    url.protocol = "https:";
    url.host = ORIGIN;
    const response = await fetch(new Request(url, request), { cache: "no-store" });
    if (key && response.ok) {
      await env.UPLOADS.put(key, String(Number(await env.UPLOADS.get(key)) + 1), { expirationTtl: 172800 });
    }
    return response;
  },
};
