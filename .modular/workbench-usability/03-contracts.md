# Contracts

```js
createTraceView(host, { maxRecords?, frameRecordBudget? })
// => { append(rawText), clear(), setActive(boolean) }
```

- `append` accepts a display string only and retains at most `maxRecords`.
- `setActive(true)` replaces/loading-renders the retained records in chunks of
  at most `frameRecordBudget` entries per animation frame.
- `setActive(false)` cancels pending visual work by changing a generation
  token; it does not discard diagnostic records.
- `clear` drops both retained records and rendered content.

```js
createAgent({ state, projector, requestScope, trace })
// trace has append(rawText)
```

```js
createDockLayout({ workspace, leftRail, rightRail, onLayoutChange?, onActivePanelsChange? })
// onActivePanelsChange receives a Set of currently active panel IDs.
```

Action buttons receive `data-action=<registered action id>` for CSS-only
hierarchy. The action renderer still emits only its existing `onAction(id)`
intent. `main.js` may treat an action result `{ status_message }` as the
status-bar message; all other actions retain `操作已完成`.
