import { api } from "./api.js";

const base = (sessionId) => `/api/geoint/sessions/${encodeURIComponent(sessionId)}/imports`;

/** HTTP-only transport: raw file bytes never pass through the JSON helper. */
export function createImportClient() {
  return {
    capabilities: (sessionId) => api(`${base(sessionId)}/capabilities`),
    list: (sessionId) => api(base(sessionId)),
    create: (sessionId, files, clientRequestId) => api(base(sessionId), { method: "POST", body: JSON.stringify({ files, client_request_id: clientRequestId }) }),
    inspect: (sessionId, importId, expectedRevision) => api(`${base(sessionId)}/${encodeURIComponent(importId)}/inspect`, { method: "POST", body: JSON.stringify({ expected_revision: expectedRevision }) }),
    commit: (sessionId, importId, expectedRevision, datasets) => api(`${base(sessionId)}/${encodeURIComponent(importId)}/commit`, { method: "POST", body: JSON.stringify({ expected_revision: expectedRevision, datasets, add_to_map: true }) }),
    async upload(sessionId, importId, file, fileId, { signal, onProgress = () => {} } = {}) {
      const url = `${base(sessionId)}/${encodeURIComponent(importId)}/files/${encodeURIComponent(fileId)}`;
      return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("PUT", url); request.setRequestHeader("Content-Type", "application/octet-stream");
        request.upload.onprogress = (event) => onProgress(event.lengthComputable ? event.loaded / event.total : 0);
        request.onerror = () => reject(new Error("上传连接中断"));
        request.onabort = () => reject(new DOMException("上传已取消", "AbortError"));
        request.onload = () => {
          let body = null; try { body = request.responseText ? JSON.parse(request.responseText) : null; } catch { body = request.responseText; }
          if (request.status >= 200 && request.status < 300) resolve(body);
          else reject(new Error(body?.detail || `上传失败（HTTP ${request.status}）`));
        };
        if (signal) signal.addEventListener("abort", () => request.abort(), { once: true });
        request.send(file);
      });
    },
  };
}
