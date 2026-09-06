/** Bounded, animation-frame trace projection for the diagnostic panel. */
export function createTraceView(host, {
  maxRecords = 1200,
  maxRecordChars = 12000,
  frameRecordBudget = 80,
  schedule = (callback) => requestAnimationFrame(callback),
  cancel = (handle) => cancelAnimationFrame(handle),
  createTextNode = (text) => document.createTextNode(text),
} = {}) {
  let records = [], active = false, rendered = 0, frame = null, generation = 0;
  const empty = () => host.replaceChildren(createTextNode("暂无活动执行。"));
  const stop = () => { if (frame !== null) cancel(frame); frame = null; };
  function scheduleDrain() {
    if (!active || frame !== null || rendered >= records.length) return;
    const expected = generation;
    frame = schedule(() => {
      frame = null;
      if (!active || expected !== generation) return;
      const end = Math.min(records.length, rendered + frameRecordBudget);
      host.append(createTextNode(`${records.slice(rendered, end).join("\n")}\n`));
      rendered = end;
      scheduleDrain();
    });
  }
  function resetRendering() {
    generation += 1; stop(); rendered = 0;
    if (active) {
      host.replaceChildren(createTextNode(records.length ? "正在加载追踪记录…\n" : "暂无活动执行。"));
      scheduleDrain();
    }
  }
  return {
    append(value) {
      const raw = String(value ?? "");
      records.push(raw.length > maxRecordChars ? `${raw.slice(0, maxRecordChars)}\n… 已截断单条追踪记录` : raw);
      if (records.length > maxRecords) { records = records.slice(-maxRecords); resetRendering(); }
      else scheduleDrain();
    },
    clear() { records = []; generation += 1; stop(); rendered = 0; empty(); },
    setActive(next) { const shouldRender = Boolean(next); if (active === shouldRender) return; active = shouldRender; if (!active) { generation += 1; stop(); return; } resetRendering(); },
    snapshot() { return [...records]; },
  };
}
