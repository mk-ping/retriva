const API_BASE = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("retriva_token");
}
function setToken(token) {
  localStorage.setItem("retriva_token", token);
}
function clearToken() {
  localStorage.removeItem("retriva_token");
}
function getStoredUser() {
  const raw = localStorage.getItem("retriva_user");
  return raw ? JSON.parse(raw) : null;
}
function setStoredUser(user) {
  localStorage.setItem("retriva_user", JSON.stringify(user));
}

async function apiRequest(path, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    localStorage.removeItem("retriva_user");
    if (!window.location.pathname.endsWith("auth.html") && !window.location.pathname.endsWith("index.html") && window.location.pathname !== "/") {
      window.location.href = "auth.html";
    }
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

const api = {
  debugRetrieve: (kbId, query) => apiRequest(`/api/chats/debug/retrieve?knowledge_base_id=${kbId}`, { method: "POST", body: JSON.stringify({ query }) }),
  searchChats: (q) => apiRequest(`/api/chats/search/all?q=${encodeURIComponent(q)}`),
  setFeedback: (chatId, messageId, feedback) =>
    apiRequest(`/api/chats/${chatId}/messages/${messageId}/feedback`, { method: "POST", body: JSON.stringify({ feedback }) }),
  signup: (name, email, password) =>
    apiRequest("/api/auth/signup", { method: "POST", body: JSON.stringify({ name, email, password }) }),
  login: (email, password) =>
    apiRequest("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => apiRequest("/api/auth/me"),
  listKBs: () => apiRequest("/api/knowledge-bases"),
  createKB: (name, description) =>
    apiRequest("/api/knowledge-bases", { method: "POST", body: JSON.stringify({ name, description }) }),
  getKB: (kbId) => apiRequest(`/api/knowledge-bases/${kbId}`),
  deleteKB: (kbId) => apiRequest(`/api/knowledge-bases/${kbId}`, { method: "DELETE" }),
  uploadDocument: (kbId, file, allowDuplicate = false) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiRequest(`/api/knowledge-bases/${kbId}/documents?allow_duplicate=${allowDuplicate}`, { method: "POST", body: fd });
  },
  reprocessDocument: (kbId, docId) =>
    apiRequest(`/api/knowledge-bases/${kbId}/documents/${docId}/reprocess`, { method: "POST" }),
  deleteDocument: (kbId, docId) =>
    apiRequest(`/api/knowledge-bases/${kbId}/documents/${docId}`, { method: "DELETE" }),
  listChats: (kbId) => apiRequest(`/api/chats?knowledge_base_id=${kbId}`),
  createChat: (kbId, title) =>
    apiRequest("/api/chats", { method: "POST", body: JSON.stringify({ knowledge_base_id: kbId, title }) }),
  getChat: (chatId) => apiRequest(`/api/chats/${chatId}`),
  renameChat: (chatId, title) =>
    apiRequest(`/api/chats/${chatId}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteChat: (chatId) => apiRequest(`/api/chats/${chatId}`, { method: "DELETE" }),
  sendMessage: (chatId, content) =>
    apiRequest(`/api/chats/${chatId}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
};

async function streamMessage(chatId, content, signal) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return res.body.getReader();
}
