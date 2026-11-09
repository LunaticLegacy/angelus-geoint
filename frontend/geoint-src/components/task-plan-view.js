import { escapeHtml } from "../dom.js";

/** Lifecycle states the console can persist for one plan leaf. */
export const PLAN_STATUSES = ["not_started", "in_progress", "completed", "blocked"];
const STATUS_LABELS = { not_started: "未开始", in_progress: "进行中", completed: "已完成", blocked: "受阻" };

/** Return the root task array from either projection key the API may use. */
export function planTasks(plan) {
  if (!plan || typeof plan !== "object") return [];
  if (Array.isArray(plan.tasks)) return plan.tasks;
  return Array.isArray(plan.plan) ? plan.plan : [];
}

/**
 * Render one recursive plan item as markup for the GEOINT plan panel.
 *
 * Leaf tasks get a status selector because `PATCH /plan/tasks/{id}` is the
 * documented transition surface. Parent status is derived by the console from
 * its children, so parents only advertise that fact instead of pretending to
 * be directly editable.
 *
 * Args:
 *   task: Task object with id, title, description, status, priority,
 *     estimated_minutes, and nested subtasks.
 *   depth: Nesting level, used only for the CSS depth class.
 *
 * Returns:
 *   Escaped HTML for the task and all of its descendants.
 */
export function renderTaskPlanItem(task, depth = 0) {
  const value = task && typeof task === "object" ? task : {};
  const level = Math.max(0, Number(depth) || 0);
  const children = Array.isArray(value.subtasks) ? value.subtasks : [];
  const status = Object.hasOwn(STATUS_LABELS, value.status) ? value.status : "not_started";
  const estimate = Number(value.estimated_minutes);
  const meta = [typeof value.priority === "string" ? value.priority.trim() : "", estimate > 0 ? `${estimate} 分钟` : ""].filter(Boolean).join(" · ");
  const control = children.length
    ? `<span class="task-state-derived" title="父任务状态由子任务派生">子项派生</span>`
    : `<select class="task-state-select ${status}" data-task-id="${escapeHtml(value.id)}" data-status="${status}" aria-label="任务状态">${PLAN_STATUSES.map((key) => `<option value="${key}"${key === status ? " selected" : ""}>${STATUS_LABELS[key]}</option>`).join("")}</select>`;
  const description = typeof value.description === "string" && value.description.trim()
    ? `<p class="task-description">${escapeHtml(value.description)}</p>`
    : "";
  const subtasks = children.length
    ? `<div class="task-children">${children.map((child) => renderTaskPlanItem(child, level + 1)).join("")}</div>`
    : "";
  return `<article class="task-block depth-${level}"><div class="task-block-head"><span class="task-dot ${status}"></span><div class="task-block-title"><strong>${escapeHtml(value.title || "未命名任务")}</strong><p>${escapeHtml(meta)}</p></div>${control}</div>${description}${subtasks}</article>`;
}

/**
 * Render one Agent's complete plan: owner line, rationale, and the task tree.
 *
 * Args:
 *   plan: Plan projection returned by GET /plan.
 *   options.agent: Agent identity the plan belongs to.
 *   options.agentLabel: Human label for that identity.
 *
 * Returns:
 *   Escaped HTML for the whole plan, including explicit empty states.
 */
export function renderPlanDocument(plan, { agent = "coordinator", agentLabel = "" } = {}) {
  const tasks = planTasks(plan);
  const label = agentLabel || (agent === "coordinator" ? "协调者" : String(agent));
  const goal = typeof plan?.goal === "string" ? plan.goal.trim() : "";
  const summary = typeof plan?.summary === "string" ? plan.summary.trim() : "";
  const head = tasks.length
    ? `<p class="plan-goal"><strong>${escapeHtml(label)}</strong> · ${tasks.length} 项根任务${goal ? ` · ${escapeHtml(goal)}` : ""}</p>`
    : `<p class="plan-goal"><strong>${escapeHtml(label)}</strong> 尚未建立任务计划。</p>`;
  const rationale = summary ? `<p class="plan-summary">${escapeHtml(summary)}</p>` : "";
  const body = tasks.length
    ? `<div class="task-plan-tree">${tasks.map((task) => renderTaskPlanItem(task)).join("")}</div>`
    : `<p class="empty">尚未建立任务计划。Agent 写入计划后会自动出现在这里。</p>`;
  return `${head}${rationale}${body}`;
}
