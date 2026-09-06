/** Render a server-owned evidence ledger without creating client-side state. */
function text(value) { return value == null || value === "" ? "—" : String(value); }

export function renderEvidencePanel(panel, snapshot, assets = []) {
  if (!panel) return;
  const records = Array.isArray(snapshot?.records) ? snapshot.records : [];
  const summary = snapshot?.summary || {};
  const names = new Map((assets || []).map((asset) => [asset.id, asset.name || asset.id]));
  const score = panel.querySelector("#risk-score");
  const level = panel.querySelector("#risk-level");
  const mode = panel.querySelector("#risk-mode");
  if (score) score.textContent = summary.risk_score == null ? "—" : text(summary.risk_score);
  if (level) level.textContent = text(summary.risk_level || summary.status);
  if (mode) mode.textContent = records.length ? "以下记录可回溯到会话资产、派生任务或知识引用。" : "运行空间分析或由 Agent 记录可追溯证据后显示。";
  const grid = panel.querySelector("#summary-grid");
  if (grid) grid.innerHTML = [
    ["来源资产", summary.asset_count || 0], ["派生任务", summary.derivation_count || 0],
    ["证据条目", summary.evidence_count || 0], ["状态", summary.status || "尚无证据"],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${text(value)}</strong></div>`).join("");
  const list = panel.querySelector("#evidence-list");
  if (!list) return;
  if (!records.length) { list.innerHTML = '<p class="empty">尚无会话级证据。完成派生任务并读取结果后会自动登记；Agent 也可记录带来源引用的判断。</p>'; return; }
  list.replaceChildren(...records.map((record) => {
    const item = document.createElement("article"); item.className = "evidence-record";
    const refs = record.source_asset_ids.map((id) => names.get(id) || id).join("、") || "无资产引用";
    const sources = [refs, record.derivation_job_id ? `任务 ${record.derivation_job_id}` : "", ...(record.knowledge_ids || [])].filter(Boolean).join(" · ");
    item.innerHTML = `<header><b>${record.kind === "derivation" ? "派生结果" : "调查判断"}</b><small>${text(record.indicator || "未标注指标")} · 可信度 ${Math.round(Number(record.confidence || 0) * 100)}%</small></header><p>${text(record.claim)}</p><footer>${sources}</footer>`;
    return item;
  }));
}
