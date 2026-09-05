# Dependency graph

`main -> workspace-ui, workspace-state, map-core, controllers`

`controllers -> api-client, workspace-state, dom`

`workspace-ui -> controllers, workspace-state`

`map-core -> api-client`

`layer-panel -> workspace-ui`

`main -> dock-layout`

`main -> map-edge-resizers`

`main -> bottom-dock-resizer`

`main -> investigation-chat, investigation-event-projector`

`agent-controller -> investigation-event-projector`

`investigation-chat -> investigation-event-projector, tool-result-renderer,
markdown-renderer`


There are no reverse edges and no controller-to-map edge.
