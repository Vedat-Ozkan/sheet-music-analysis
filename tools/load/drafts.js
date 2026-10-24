import http from "k6/http";
import { check } from "k6";
import { Trend, Rate } from "k6/metrics";

const URL = __ENV.URL;
const TOKEN = __ENV.TOKEN;
const SCORE_ID = __ENV.SCORE_ID;
const INPUTS = JSON.parse(open(__ENV.INPUTS));
const RENDER_SHARE = Number(__ENV.RENDER_SHARE || 0.3);

const latency = { draft_from_notes: new Trend("draft_ms", true), render_analysis: new Trend("render_ms", true) };
const failed = new Rate("tool_failed");

const STEPS = (__ENV.STEPS || "1,2,4,8").split(",").map(Number);
const STEP = __ENV.STEP || "2m";
const SCENARIOS = {
  ramp: { executor: "ramping-vus", startVUs: STEPS[0], stages: STEPS.flatMap((vus) => [{ duration: "10s", target: vus }, { duration: STEP, target: vus }]) },
  spike: { executor: "ramping-vus", startVUs: 0, stages: [{ duration: "5s", target: Number(__ENV.PEAK || 8) }, { duration: "3m", target: Number(__ENV.PEAK || 8) }] },
  soak: { executor: "constant-vus", vus: Number(__ENV.VUS || 1), duration: __ENV.DURATION || "30m" },
  once: { executor: "per-vu-iterations", vus: 1, iterations: 1 },
};

export const options = {
  scenarios: { load: SCENARIOS[__ENV.SCENARIO || "ramp"] },
  thresholds: {
    tool_failed: [{ threshold: "rate<0.01", abortOnFail: __ENV.ABORT === "1", delayAbortEval: "30s" }],
    draft_ms: [{ threshold: `p(99)<${__ENV.P99_MS || 5000}`, abortOnFail: __ENV.ABORT === "1", delayAbortEval: "30s" }],
  },
  summaryTrendStats: ["count", "med", "p(95)", "p(99)", "max"],
};

function call(name, args) {
  const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } });
  const response = http.post(URL, body, {
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream",
               "user-agent": "Claude-User", authorization: `Bearer ${TOKEN}` },
    timeout: "300s",
    tags: { tool: name },
  });
  latency[name].add(response.timings.duration);
  let ok = response.status === 200;
  try {
    ok = ok && response.json("result.isError") !== true;
  } catch (error) {
    ok = false;
  }
  failed.add(!ok);
  check(response, { [`${name} ok`]: () => ok });
}

export default function () {
  if (SCORE_ID && Math.random() < RENDER_SHARE) {
    call("render_analysis", { score_id: SCORE_ID, annotations: INPUTS.render.annotations, measure_range: INPUTS.render.measure_range });
  } else {
    const item = INPUTS.note_lists[Math.floor(Math.random() * INPUTS.note_lists.length)];
    call("draft_from_notes", { notes: item.notes });
  }
}
