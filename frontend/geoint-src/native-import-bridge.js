/**
 * Optional desktop bridge. Browser builds have no Tauri global and remain on
 * the ordinary FileList path. Native paths never cross this JS boundary.
 *
 * Opening the session directory is *not* a desktop-only capability: it is a
 * documented HTTP route (POST /api/sessions/{id}/open-folder) served by the
 * backend, so it lives in api.js and works in both shells.
 */
export function createNativeImportBridge(onEvent) {
  const tauri = globalThis.__TAURI__;
  if (!tauri?.core?.invoke || !tauri?.event?.listen) {
    return { available: false, setSession: async () => {}, chooseFiles: async () => false, dispose: async () => {} };
  }
  let unlisten = null;
  const listening = tauri.event.listen("geoint://native-import", (event) => onEvent(event.payload)).then((stop) => { unlisten = stop; });
  return {
    available: true,
    async setSession(sessionId) { await tauri.core.invoke("set_geoint_import_session", { sessionId: sessionId || null }); },
    async chooseFiles() { await tauri.core.invoke("choose_geoint_import_files"); return true; },
    async dispose() { await listening; await unlisten?.(); },
  };
}
