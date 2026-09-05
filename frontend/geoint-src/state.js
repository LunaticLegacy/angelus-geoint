export function createWorkspaceState() {
  let selectedSession = localStorage.getItem("angelus.geoint.selected-session.v1") || "";
  let profile = null, connectors = [];
  return {
    selectSession(id) { selectedSession = id || ""; selectedSession ? localStorage.setItem("angelus.geoint.selected-session.v1", selectedSession) : localStorage.removeItem("angelus.geoint.selected-session.v1"); },
    sessionId: () => selectedSession,
    setProfile: (value) => { profile = value; }, profile: () => profile,
    setConnectors: (value) => { connectors = value || []; }, connectors: () => connectors,
  };
}
