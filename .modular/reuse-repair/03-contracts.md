# Contracts

`core.geoint_runtime` exposes `service`, `catalog`, `derivations`, `presentation`, `downloads`; its service catalog and presentation are identity-equal to tool/API values.

Catalog `register_managed_asset(local_path, ...)` records an internal managed locator. `bound_path(session_id, asset_id)` resolves either a granted source or managed file after capability checking; managed source files remain hidden.

Representation descriptor: `{kind: vector|cog, asset_id, url, projection, extent}` only when actually readable. Unsupported formats are a domain error, never fake XYZ. Existing tile route remains 501 but is no longer advertised.

`api()` throws `ApiError(status, message, issues)`; message is a deterministic text summary for FastAPI validation arrays. `createSessionRequestScope(state)` has `run(fn)` / `isCurrent(token)`; stale responses cannot mutate view.

Every session-bound controller, including Agent history/status and EventSource fallback, captures a request-scope token before async work; EventSource payloads must match both its session and active token.

Safe remote download validates scheme/hostname and all resolved IPs before every request and redirect. Redirects are disabled in stdlib and performed only after validating the next Location, with max 3 hops.
