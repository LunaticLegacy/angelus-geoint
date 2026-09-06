import assert from "node:assert/strict";
import { createTraceView } from "./trace-view.js";

const queued = [], host = { nodes: [], replaceChildren(...nodes) { this.nodes = nodes; }, append(...nodes) { this.nodes.push(...nodes); } };
const trace = createTraceView(host, { maxRecords: 3, frameRecordBudget: 1, schedule: (callback) => { queued.push(callback); return queued.length - 1; }, cancel: () => {}, createTextNode: (text) => text });
trace.append("one"); trace.append("two"); trace.append("three"); trace.append("four");
assert.equal(trace.snapshot().join("|"), "two|three|four");
trace.setActive(true);
while (queued.length) queued.shift()();
assert.match(host.nodes.join(""), /two/); assert.match(host.nodes.join(""), /four/);
trace.clear(); assert.deepEqual(trace.snapshot(), []); assert.equal(host.nodes.join(""), "暂无活动执行。");
console.log("Incremental trace view checks passed.");
