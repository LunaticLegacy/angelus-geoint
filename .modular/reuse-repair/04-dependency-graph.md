# Dependency graph

core -> geoint-runtime -> service/catalog/derivations/presentation
API adapter -> geoint-runtime -> representation-projection/catalog
Tool provider -> geoint-runtime -> safe-http-download/catalog
presentation -> atomic-json primitive
main/controllers -> session-request-scope/api-client
map-core -> representation descriptor

Forbidden: API -> direct durable GEOINT constructor; ToolProvider -> direct durable GEOINT constructor; map-core -> catalog/API strings; controller -> structured error internals; downloader -> catalog persistence.

Graph is acyclic. Architecture status: PASS.
