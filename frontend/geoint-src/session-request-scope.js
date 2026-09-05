/**
 * Gives UI requests a selected-session identity and a per-surface revision.
 *
 * A controller captures a token before awaiting.  It may change the DOM only
 * while that token still represents the selected session and latest request
 * for its own surface.  The scope owns selection changes so A -> B -> A is
 * still distinguishable from the original A request.
 */
export function createSessionRequestScope(state) {
  let knownSession = state.sessionId();
  let sessionRevision = 0;
  const requests = new Map();

  function synchronize() {
    const current = state.sessionId();
    if (current !== knownSession) {
      knownSession = current;
      sessionRevision += 1;
    }
  }

  function select(sessionId) {
    state.selectSession(sessionId);
    synchronize();
    return knownSession;
  }

  function capture(surface = "default") {
    synchronize();
    const request = (requests.get(surface) || 0) + 1;
    requests.set(surface, request);
    return Object.freeze({ sessionId: knownSession, sessionRevision, surface, request });
  }

  function isCurrent(token) {
    synchronize();
    return Boolean(token)
      && token.sessionId === knownSession
      && token.sessionRevision === sessionRevision
      && requests.get(token.surface) === token.request;
  }

  return { select, capture, isCurrent };
}
