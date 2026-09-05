# Reuse repair

Goal: repair every confirmed reuse boundary defect without changing Angelus Session/run/connector public contracts. Scope is mounted GEOINT backend and Vite frontend. Existing dirty changes are preserved.

Confirmed defects: duplicated GEOINT process state in API/tool provider; non-atomic map document persistence; remote files register without a supported catalog locator; representation type guessed by consumers; front-end structured API errors stringify as `[object Object]`; response work is not consistently scoped to selected session; remote tool follows redirects before validating each network hop.

Non-goals: the planned external import workflow, raster tile generation, all existing metadata limitations, and broad visual redesign.
