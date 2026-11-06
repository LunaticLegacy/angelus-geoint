import assert from "node:assert/strict";
import { PLAN_STATUSES, planTasks, renderPlanDocument, renderTaskPlanItem } from "./task-plan-view.js";
import { planPath } from "./task-plan-panel.js";

// --- URL construction -------------------------------------------------------
assert.equal(planPath("abc"), "/api/sessions/abc/plan?agent=coordinator");
assert.equal(planPath("a b/c", { agent: "coordinator" }), "/api/sessions/a%20b%2Fc/plan?agent=coordinator");
assert.equal(planPath("abc", { suffix: "/tasks/t-1", agent: "coordinator" }), "/api/sessions/abc/plan/tasks/t-1?agent=coordinator");
assert.equal(planPath("abc", { agent: "worker 1" }), "/api/sessions/abc/plan?agent=worker%201");

// --- Root task extraction (tasks key wins, legacy plan key still understood) --
assert.deepEqual(planTasks({ tasks: [1, 2] }), [1, 2]);
assert.deepEqual(planTasks({ plan: [3] }), [3]);
assert.deepEqual(planTasks(null), []);
assert.deepEqual(planTasks({}), []);

// --- Leaf rendering --------------------------------------------------------
assert.deepEqual(PLAN_STATUSES, ["not_started", "in_progress", "completed", "blocked"]);
const leaf = renderTaskPlanItem({ id: "t1", title: "抓取数据", status: "in_progress", priority: "high", estimated_minutes: 30, description: "下载公开数据" });
assert.match(leaf, /class="task-block depth-0"/);
assert.match(leaf, /<strong>抓取数据<\/strong>/);
assert.match(leaf, /high · 30 分钟/);
assert.match(leaf, /<select class="task-state-select in_progress" data-task-id="t1" data-status="in_progress"/);
assert.match(leaf, /<option value="in_progress" selected>进行中<\/option>/);
assert.match(leaf, /<option value="blocked">受阻<\/option>/);
assert.match(leaf, /class="task-description">下载公开数据</);
assert.doesNotMatch(leaf, /子项派生/);

// Unknown/absent status falls back to not_started instead of rendering nothing.
const fallback = renderTaskPlanItem({ id: "t2", title: "x", status: "exploded" });
assert.match(fallback, /data-status="not_started"/);
assert.match(fallback, /<option value="not_started" selected>未开始<\/option>/);

// Parent tasks derive their state from children, so they expose no selector.
const parent = renderTaskPlanItem({ id: "p", title: "父任务", status: "in_progress", subtasks: [{ id: "c", title: "子任务", status: "completed" }] });
assert.match(parent, /子项派生/);
assert.doesNotMatch(parent.slice(0, parent.indexOf("task-children")), /task-state-select/);
assert.match(parent, /class="task-block depth-1"/);

// --- XSS: every interpolated field stays escaped ----------------------------
const hostile = renderTaskPlanItem({
  id: '"><img src=x onerror=alert(1)>',
  title: "<script>alert(2)</script>",
  description: "& <b>bad</b>",
  priority: "<i>",
  status: "not_started",
});
assert.doesNotMatch(hostile, /<script>/);
assert.doesNotMatch(hostile, /<img/);
assert.doesNotMatch(hostile, /<b>bad<\/b>/);
assert.match(hostile, /&lt;script&gt;alert\(2\)&lt;\/script&gt;/);
assert.match(hostile, /data-task-id="&quot;&gt;&lt;img src=x onerror=alert\(1\)&gt;"/);

// --- Whole document --------------------------------------------------------
const empty = renderPlanDocument({ goal: "", summary: "", tasks: [] }, { agent: "coordinator" });
assert.match(empty, /<strong>协调者<\/strong> 尚未建立任务计划。/);
assert.match(empty, /尚未建立任务计划。Agent 写入计划后会自动出现在这里。/);

const document = renderPlanDocument({ goal: "完成调查", summary: "先取数再分析", tasks: [{ id: "a", title: "取数" }] }, { agent: "coordinator" });
assert.match(document, /<strong>协调者<\/strong> · 1 项根任务 · 完成调查/);
assert.match(document, /class="plan-summary">先取数再分析</);
assert.match(document, /<div class="task-plan-tree"><article/);

// Legacy `plan` key is accepted, and a non-coordinator label falls back to the id.
const legacy = renderPlanDocument({ plan: [{ id: "a", title: "取数" }] }, { agent: "worker-2" });
assert.match(legacy, /<strong>worker-2<\/strong> · 1 项根任务/);
assert.match(legacy, /data-task-id="a"/);

console.log("Task plan view checks passed.");
