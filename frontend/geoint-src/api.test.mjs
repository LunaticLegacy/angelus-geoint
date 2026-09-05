import assert from "node:assert/strict";
import { api, ApiError } from "./api.js";

let request;
globalThis.fetch = async (_url, options) => {
  request = options;
  return {
    ok: false,
    status: 422,
    statusText: "Unprocessable Entity",
    text: async () => JSON.stringify({ detail: [
      { type: "missing", loc: ["body", "source", "url"], msg: "Field required" },
      { type: "value_error", loc: ["body", "max_zoom"], msg: "must be less than 23" },
    ] }),
  };
};

await assert.rejects(
  () => api("/api/example", { headers: { "X-Request-ID": "test" } }),
  (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 422);
    assert.equal(error.message, "请求校验失败：source.url：Field required；max_zoom：must be less than 23");
    assert.equal(error.validationErrors.length, 2);
    assert.equal(error.message.includes("[object Object]"), false);
    return true;
  },
);
assert.equal(request.headers["Content-Type"], "application/json");
assert.equal(request.headers["X-Request-ID"], "test");

globalThis.fetch = async () => ({ ok: true, status: 200, statusText: "OK", text: async () => "not-json" });
assert.equal(await api("/api/text"), "not-json");
console.log("API error normalization checks passed.");
