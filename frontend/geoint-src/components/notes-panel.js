import { api } from "../api.js";
import { escapeHtml } from "../dom.js";

/** Note scopes the NoteStore exposes over HTTP. */
export const NOTE_SCOPES = ["session", "project"];
const MAX_TAGS = 32, MAX_TAG_CHARS = 64, MAX_CONTENT_CHARS = 100_000;

/** Build the documented notes URL for a list or one note. */
export function notesPath(sessionId, { scope = "session", noteId = "" } = {}) {
  const base = `/api/sessions/${encodeURIComponent(sessionId)}/notes`;
  return noteId ? `${base}/${encodeURIComponent(scope)}/${encodeURIComponent(noteId)}` : base;
}

/** Build the list query string, omitting an empty search term. */
export function notesQuery({ scope = "session", query = "" } = {}) {
  const params = new URLSearchParams({ scope });
  const value = String(query ?? "").trim();
  if (value) params.set("query", value);
  return `?${params.toString()}`;
}

/**
 * Split a comma separated tag field into the shapes NoteStore accepts.
 *
 * Tags are de-duplicated in first-seen order and clamped to the server limits
 * (32 tags, 64 characters each) so the panel cannot post a payload the API
 * would reject.
 */
export function parseNoteTags(text) {
  const seen = new Set();
  for (const raw of String(text ?? "").split(/[,，]/)) {
    const tag = raw.trim().slice(0, MAX_TAG_CHARS);
    if (tag) seen.add(tag);
    if (seen.size >= MAX_TAGS) break;
  }
  return [...seen];
}

/** One-line preview of a note body for the list row. */
export function notePreview(content, limit = 100) {
  const text = String(content ?? "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

/**
 * Render the note list.
 *
 * Args:
 *   notes: Note projections from GET /notes.
 *   selectedId: Currently opened note id, or an empty string.
 *   options.sessionId: Selected Session; drives the empty-state wording.
 *
 * Returns:
 *   Escaped HTML. Titles and previews are Agent/user-authored text, so both
 *   must stay escaped.
 */
export function renderNotesList(notes, selectedId = "", { sessionId = "" } = {}) {
  if (!Array.isArray(notes) || !notes.length) {
    return `<p class="notes-empty">${sessionId ? "暂无笔记" : "尚未选择会话"}</p>`;
  }
  return notes.map((note) => {
    const id = String(note?.note_id ?? "");
    const active = id && id === selectedId;
    return `<button type="button" class="notes-item${active ? " selected" : ""}" data-note-id="${escapeHtml(id)}" role="listitem"><strong>${escapeHtml(note?.title || "未命名笔记")}</strong><span>${escapeHtml(notePreview(note?.content))}</span></button>`;
  }).join("");
}

/**
 * Mount the Session/Project note panel.
 *
 * Wires the four documented NoteStore methods: list (GET), create (POST),
 * update (PATCH with optimistic revision), delete (DELETE with revision).
 * Every failure is rendered in the panel and mirrored to the status bar.
 *
 * Args:
 *   root: Panel host element.
 *   options.onStatus: Callback for the shell status bar messages.
 *
 * Returns:
 *   `setSession(id)` / `refresh()` handles used by the session lifecycle.
 */
export function mountNotesPanel(root, { onStatus = () => {} } = {}) {
  let sessionId = "", scope = "session", query = "", notes = [], selected = null, loading = false, searchTimer = null;
  if (!root) return { setSession() {}, refresh() {} };
  root.innerHTML = `<div class="section-title compact"><div><span class="eyebrow">DURABLE NOTES</span><h3>笔记</h3></div><div class="action-group"><button type="button" class="notes-new primary">新建</button></div></div><p class="fineprint">笔记持久化保存在会话（或绑定项目）中，可被 Agent 的笔记工具读取；保存时携带版本号，冲突会被后端拒绝。</p><div class="notes-toolbar"><label class="field notes-scope-field"><span>范围</span><select class="notes-scope" aria-label="笔记范围"><option value="session">会话</option><option value="project">项目</option></select></label><label class="field notes-search-field"><span>搜索</span><input class="notes-search" type="search" placeholder="搜索标题或内容…" aria-label="搜索笔记" /></label></div><div class="notes-error" role="alert" hidden></div><div class="notes-list" role="list" aria-live="polite"></div><div class="notes-editor-wrap" hidden><div class="notes-editor-head"><strong class="notes-editor-title">编辑笔记</strong><button type="button" class="notes-delete danger">删除</button></div><label class="field"><span>标题</span><input class="notes-title" maxlength="200" placeholder="标题" /></label><label class="field"><span>内容</span><textarea class="notes-editor" rows="8" placeholder="记录想法、待办或运行线索…"></textarea></label><label class="field"><span>标签（逗号分隔，可选）</span><input class="notes-tags" placeholder="例如：数据源, 待核实" /></label><div class="notes-footer"><span class="notes-status" role="status" aria-live="polite"></span><span class="notes-count">0 字</span><button type="button" class="notes-save primary">保存</button></div></div>`;
  const list = root.querySelector(".notes-list");
  const editorWrap = root.querySelector(".notes-editor-wrap");
  const editorTitle = root.querySelector(".notes-editor-title");
  const title = root.querySelector(".notes-title");
  const editor = root.querySelector(".notes-editor");
  const tags = root.querySelector(".notes-tags");
  const status = root.querySelector(".notes-status");
  const count = root.querySelector(".notes-count");
  const error = root.querySelector(".notes-error");
  const setError = (message = "") => { error.textContent = message; error.hidden = !message; };
  const updateCount = () => { count.textContent = `${editor.value.length.toLocaleString()} / ${MAX_CONTENT_CHARS.toLocaleString()} 字`; };

  function renderList() { list.innerHTML = renderNotesList(notes, selected?.note_id || "", { sessionId }); }
  function loadEditor() {
    editorWrap.hidden = !selected;
    if (!selected) return;
    editorTitle.textContent = selected.note_id ? "编辑笔记" : "新建笔记";
    title.value = selected.title;
    editor.value = selected.content;
    tags.value = (selected.tags || []).join(", ");
    status.textContent = selected.note_id ? `版本 ${selected.revision}` : "尚未保存";
    updateCount();
  }

  async function load() {
    if (!sessionId) { notes = []; selected = null; setError(""); renderList(); loadEditor(); return null; }
    loading = true;
    setError("");
    try {
      const payload = await api(`${notesPath(sessionId)}${notesQuery({ scope, query })}`);
      notes = Array.isArray(payload?.notes) ? payload.notes : [];
      if (selected && !notes.some((note) => note.note_id === selected.note_id)) { selected = null; }
      renderList();
      loadEditor();
      return notes;
    } catch (caught) {
      notes = [];
      setError(`笔记加载失败：${caught.message}`);
      renderList();
      return null;
    } finally {
      loading = false;
    }
  }

  async function save() {
    if (!sessionId || !selected || loading) return;
    if (editor.value.length > MAX_CONTENT_CHARS) { setError(`笔记内容超过 ${MAX_CONTENT_CHARS.toLocaleString()} 字上限。`); return; }
    loading = true;
    setError("");
    status.textContent = "保存中…";
    const payload = {
      scope: selected.scope || scope,
      title: title.value,
      content: editor.value,
      tags: parseNoteTags(tags.value),
      ...(selected.note_id ? { revision: selected.revision } : {}),
    };
    const target = notesPath(sessionId, { scope: payload.scope, noteId: selected.note_id });
    try {
      const saved = selected.note_id
        ? await api(target, { method: "PATCH", body: JSON.stringify(payload) })
        : await api(notesPath(sessionId), { method: "POST", body: JSON.stringify(payload) });
      selected = saved;
      status.textContent = `已保存 · 版本 ${saved.revision}`;
      onStatus(`笔记“${saved.title}”已保存。`);
      await load();
    } catch (caught) {
      status.textContent = "保存失败";
      setError(`笔记保存失败：${caught.message}`);
    } finally {
      loading = false;
    }
  }

  async function remove() {
    if (!sessionId || !selected?.note_id || loading) return;
    if (!globalThis.confirm(`删除笔记“${selected.title || "未命名笔记"}”？`)) return;
    loading = true;
    setError("");
    try {
      await api(`${notesPath(sessionId, { scope: selected.scope, noteId: selected.note_id })}?revision=${encodeURIComponent(selected.revision)}`, { method: "DELETE" });
      const removed = selected.title;
      selected = null;
      onStatus(`笔记“${removed || "未命名笔记"}”已删除。`);
      await load();
    } catch (caught) {
      setError(`笔记删除失败：${caught.message}`);
    } finally {
      loading = false;
    }
  }

  root.querySelector(".notes-new").addEventListener("click", () => {
    if (!sessionId) { setError("请先选择会话后再新建笔记。"); return; }
    selected = { note_id: "", scope, title: "", content: "", tags: [], status: "active", revision: 0 };
    setError("");
    loadEditor();
    renderList();
    title.focus();
  });
  root.querySelector(".notes-save").addEventListener("click", save);
  root.querySelector(".notes-delete").addEventListener("click", remove);
  root.querySelector(".notes-scope").addEventListener("change", (event) => { scope = event.target.value; selected = null; load(); });
  root.querySelector(".notes-search").addEventListener("input", (event) => {
    query = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 250);
  });
  list.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-note-id]");
    if (!button) return;
    selected = notes.find((note) => note.note_id === button.dataset.noteId) || null;
    setError("");
    loadEditor();
    renderList();
  });
  editor.addEventListener("input", updateCount);

  return {
    setSession(nextSessionId) { sessionId = nextSessionId || ""; selected = null; return load(); },
    refresh() { return load(); },
  };
}
