// Serves the analysis server under our own domain: OpenAI verifies the domain of the MCP address,
// and a run.app address can't carry our verification file.
const ORIGIN = "sheet-music-analysis-cx6osvvmya-uc.a.run.app";

export default {
  fetch(request) {
    const url = new URL(request.url);
    url.protocol = "https:";
    url.host = ORIGIN;
    // Drawn pages are deleted after a day (privacy policy), so Cloudflare must not keep copies.
    return fetch(new Request(url, request), { cache: "no-store" });
  },
};
