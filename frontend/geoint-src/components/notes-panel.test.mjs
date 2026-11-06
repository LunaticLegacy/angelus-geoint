import assert from "node:assert/strict";
import { NOTE_SCOPES, notePreview, notesPath, notesQuery, parseNoteTags, renderNotesList } from "./notes-panel.js";

// --- URL + query construction ----------------------------------------------
assert.deepEqual(NOTE_SCOPES, ["session", "project"]);
assert.equal(notesPath("abc"), "/api/sessions/abc/notes");
assert.equal(notesPath("a/b", { noteId: "n-1", scope: "project" }), "/api/sessions/a%2Fb/notes/project/n-1");
assert.equal(notesQuery({ scope: "session" }), "?scope=session");
assert.equal(notesQuery({ scope: "project", query: "  风险  " }), "?scope=project&query=%E9%A3%8E%E9%99%A9");
assert.equal(notesQuery({ scope: "session", query: "   " }), "?scope=session");

// --- Tag parsing is de-duplicated and clamped to the API limits -------------
assert.deepEqual(parseNoteTags("数据源, 待核实，数据源"), ["数据源", "待核实"]);
assert.deepEqual(parseNoteTags("  a ,, b ,"), ["a", "b"]);
assert.deepEqual(parseNoteTags(""), []);
assert.deepEqual(parseNoteTags(null), []);
assert.equal(parseNoteTags("x".repeat(80))[0].length, 64);
assert.equal(parseNoteTags(Array.from({ length: 40 }, (_, index) => `t${index}`).join(",")).length, 32);

// --- Preview collapses whitespace and truncates -----------------------------
assert.equal(notePreview("  a\n\n  b\t c "), "a b c");
assert.equal(notePreview("abcdef", 3), "abc…");
assert.equal(notePreview("abc", 10), "abc");
assert.equal(notePreview(undefined), "");

// --- List rendering: empty states ------------------------------------------
assert.match(renderNotesList([], "", { sessionId: "" }), /尚未选择会话/);
assert.match(renderNotesList([], "", { sessionId: "s1" }), /暂无笔记/);
assert.match(renderNotesList(null, "", { sessionId: "s1" }), /暂无笔记/);

// --- List rendering: selection + escaping ----------------------------------
const notes = [
  { note_id: "n-1", title: "正常笔记", content: "内容" },
  { note_id: "n-2", title: "<img src=x onerror=alert(1)>", content: "<script>alert(2)</script>" },
];
const list = renderNotesList(notes, "n-1", { sessionId: "s1" });
assert.match(list, /class="notes-item selected" data-note-id="n-1"/);
assert.match(list, /data-note-id="n-2"/);
assert.doesNotMatch(list, /<img/);
assert.doesNotMatch(list, /<script>/);
assert.match(list, /&lt;img src=x onerror=alert\(1\)&gt;/);
assert.match(list, /&lt;script&gt;alert\(2\)&lt;\/script&gt;/);
assert.doesNotMatch(renderNotesList(notes, "n-9", { sessionId: "s1" }), /selected/);

// Untitled notes still render a label instead of an empty button.
assert.match(renderNotesList([{ note_id: "n-3", title: "", content: "" }], "", { sessionId: "s1" }), /<strong>未命名笔记<\/strong>/);

console.log("Notes panel checks passed.");
