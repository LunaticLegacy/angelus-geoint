import assert from "node:assert/strict";
import { createNativeImportBridge } from "./native-import-bridge.js";

const previous = globalThis.__TAURI__;
const received = [], calls = [];
let listener, disposed = false;
globalThis.__TAURI__ = {
  core: { invoke: async (command, payload) => calls.push({ command, payload }) },
  event: { listen: async (name, callback) => { assert.equal(name, "geoint://native-import"); listener = callback; return () => { disposed = true; }; } },
};

const bridge = createNativeImportBridge((event) => received.push(event));
assert.equal(bridge.available, true);
await bridge.setSession("session_123");
await bridge.chooseFiles();
await bridge.openWorkspace();
listener({ payload: { type: "progress", total: 1 } });
assert.deepEqual(calls, [
  { command: "set_geoint_import_session", payload: { sessionId: "session_123" } },
  { command: "choose_geoint_import_files", payload: undefined },
  { command: "open_geoint_workspace", payload: undefined },
]);
assert.deepEqual(received, [{ type: "progress", total: 1 }]);
await bridge.dispose();
assert.equal(disposed, true);

globalThis.__TAURI__ = undefined;
assert.equal(createNativeImportBridge(() => {}).available, false);
globalThis.__TAURI__ = previous;
console.log("Native import bridge checks passed.");
