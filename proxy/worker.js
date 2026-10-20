const ORIGIN = "sheet-music-analysis-cx6osvvmya-uc.a.run.app";

export default {
  fetch(request) {
    const url = new URL(request.url);
    url.protocol = "https:";
    url.host = ORIGIN;
    return fetch(new Request(url, request), { cache: "no-store" });
  },
};
