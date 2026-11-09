/** A transport error whose message is always safe to render in a UI status area. */
export class ApiError extends Error {
  constructor(message, { status = 0, detail = null, validationErrors = [] } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.validationErrors = validationErrors;
  }
}

function validationMessage(item) {
  if (!item || typeof item !== "object") return "请求参数不符合要求";
  const location = Array.isArray(item.loc)
    ? item.loc.filter((part) => part !== "body").map(String).join(".")
    : "";
  const message = typeof item.msg === "string" && item.msg.trim() ? item.msg.trim() : "请求参数不符合要求";
  return location ? `${location}：${message}` : message;
}

function errorMessage(detail, status, statusText) {
  if (Array.isArray(detail)) {
    const messages = detail.map(validationMessage).filter(Boolean);
    return messages.length ? `请求校验失败：${messages.join("；")}` : "请求校验失败";
  }
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (detail && typeof detail === "object" && typeof detail.message === "string" && detail.message.trim()) return detail.message.trim();
  return statusText ? `${status} ${statusText}` : `请求失败（HTTP ${status}）`;
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!Object.keys(headers).some((key) => key.toLowerCase() === "content-type")) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let body = null;
  if (text) {
    try { body = JSON.parse(text); }
    catch { body = text; }
  }
  if (!response.ok) {
    const detail = body && typeof body === "object" ? body.detail : body;
    throw new ApiError(errorMessage(detail, response.status, response.statusText), {
      status: response.status,
      detail,
      validationErrors: Array.isArray(detail) ? detail : [],
    });
  }
  return body;
}
export const presentation = (sessionId) => `/api/geoint/sessions/${encodeURIComponent(sessionId)}/map-presentation`;
/** Ask the backend to reveal the session directory in the host file manager. */
export const openSessionFolder = (sessionId) => api(`/api/sessions/${encodeURIComponent(sessionId)}/open-folder`, { method: "POST" });
