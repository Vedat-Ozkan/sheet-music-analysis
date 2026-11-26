import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import worker from "./worker.js";

const OURS = { "x-answered-by": "sheet-music-analysis" };
const CLOUD_RUN_REFUSAL = () => new Response("Rate exceeded.", { status: 429 });
const realFetch = globalThis.fetch;
const realLog = console.log;

function env() {
  const kept = new Map();
  return { PROXY_KEY: "key", ADDRESS_SALT: "salt", kept,
           UPLOADS: { get: async (k) => kept.get(k) ?? null, put: async (k, v) => { kept.set(k, v); } } };
}

function origin(...answers) {
  const seen = [];
  globalThis.fetch = async (request) => {
    seen.push({ url: request.url, method: request.method, key: request.headers.get("x-proxy-key"),
                body: request.method === "GET" ? null : await request.text() });
    return answers.shift()();
  };
  return seen;
}

function logged() {
  const lines = [];
  console.log = (line) => lines.push(JSON.parse(line));
  return lines;
}

afterEach(() => {
  globalThis.fetch = realFetch;
  console.log = realLog;
});

const call = (body = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}') =>
  new Request("https://mcp.sheetmusicanalysis.com/mcp", { method: "POST", body });

test("a request Cloud Run refused is sent once more, with the same body, and the refusal is logged", async () => {
  const seen = origin(CLOUD_RUN_REFUSAL, () => new Response("answer", { status: 200, headers: OURS }));
  const lines = logged();
  const response = await worker.fetch(call(), env());
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "answer");
  assert.equal(seen.length, 2);
  assert.deepEqual(seen.map((s) => s.body), [seen[0].body, seen[0].body]);
  assert.equal(seen[0].body, '{"jsonrpc":"2.0","id":1,"method":"tools/list"}');
  assert.ok(seen.every((s) => s.key === "key" && s.url === "https://sheet-music-analysis-cx6osvvmya-uc.a.run.app/mcp"));
  assert.equal(lines.length, 1);
  assert.deepEqual({ ...lines[0], waited_ms: 0 },
                   { event: "cloud_run_refused", method: "POST", path: "/mcp", status: 429, waited_ms: 0, retry_status: 200, rescued: true });
});

test("a 500 from Cloud Run is retried too", async () => {
  const seen = origin(() => new Response("", { status: 500 }), () => new Response("answer", { status: 200, headers: OURS }));
  logged();
  assert.equal((await worker.fetch(call(), env())).status, 200);
  assert.equal(seen.length, 2);
});

for (const status of [429, 500, 503]) {
  test(`our server's own ${status} is passed on and never retried`, async () => {
    const seen = origin(() => new Response("ours", { status, headers: OURS }));
    const lines = logged();
    const response = await worker.fetch(call(), env());
    assert.equal(response.status, status);
    assert.equal(await response.text(), "ours");
    assert.equal(seen.length, 1);
    assert.deepEqual(lines, []);
  });
}

test("a 503 without our mark is not taken for a refusal", async () => {
  const seen = origin(() => new Response("", { status: 503 }));
  assert.equal((await worker.fetch(call(), env())).status, 503);
  assert.equal(seen.length, 1);
});

test("a second refusal is passed on after one retry and logged as not rescued", async () => {
  const seen = origin(CLOUD_RUN_REFUSAL, CLOUD_RUN_REFUSAL);
  const lines = logged();
  assert.equal((await worker.fetch(call(), env())).status, 429);
  assert.equal(seen.length, 2);
  assert.equal(lines[0].rescued, false);
  assert.equal(lines[0].retry_status, 429);
});

test("an upload refused by Cloud Run is sent again whole and counted once", async () => {
  const file = "x".repeat(3 * 1024 * 1024);
  const seen = origin(CLOUD_RUN_REFUSAL, () => new Response("{}", { status: 200, headers: OURS }));
  logged();
  const settings = env();
  const upload = new Request("https://mcp.sheetmusicanalysis.com/upload?id=abc", { method: "POST", body: file });
  assert.equal((await worker.fetch(upload, settings)).status, 200);
  assert.deepEqual(seen.map((s) => s.body.length), [file.length, file.length]);
  assert.deepEqual([...settings.kept.values()], ["1"]);
});

test("a GET refused by Cloud Run is retried without a body", async () => {
  const seen = origin(CLOUD_RUN_REFUSAL, () => new Response("png", { status: 200, headers: OURS }));
  logged();
  const response = await worker.fetch(new Request("https://mcp.sheetmusicanalysis.com/files/page.png"), env());
  assert.equal(await response.text(), "png");
  assert.deepEqual(seen.map((s) => [s.method, s.body]), [["GET", null], ["GET", null]]);
});

test("a streamed answer is handed on as it comes", async () => {
  let push;
  const stream = new ReadableStream({ start(controller) { push = controller; } });
  origin(() => new Response(stream, { status: 200, headers: { ...OURS, "content-type": "text/event-stream" } }));
  const reader = (await worker.fetch(call(), env())).body.getReader();
  push.enqueue(new TextEncoder().encode("data: first\n\n"));
  assert.equal(new TextDecoder().decode((await reader.read()).value), "data: first\n\n");
  push.close();
  assert.equal((await reader.read()).done, true);
});
