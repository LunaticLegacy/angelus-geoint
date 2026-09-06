# Dependency graph

```text
main -> trace-view
main -> agent-controller
main -> dock-layout
agent-controller -> injected trace-view contract
dock-layout -> injected active-panel callback
workspace-ui -> DOM only
```

No module imports another through the two injected callbacks. The directed
graph remains acyclic. No backend module or HTTP contract changes.
