const API_BASE = window.RETRIVA_API || "http://localhost:8000";

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
  deleteLastTurn: (chatId) => apiRequest(`/api/chats/${chatId}/last-turn`, { method: "DELETE" }),
  autoTitle: (chatId) => apiRequest(`/api/chats/${chatId}/title`, { method: "POST" }),
  updateKB: (kbId, name, description) => apiRequest(`/api/knowledge-bases/${kbId}`, { method: "PATCH", body: JSON.stringify({ name, description }) }),
  deleteChat: (chatId) => apiRequest(`/api/chats/${chatId}`, { method: "DELETE" }),
  sendMessage: (chatId, content, regenerate = false) =>
    apiRequest(`/api/chats/${chatId}/messages`, { method: "POST", body: JSON.stringify({ content, regenerate, search_all: window.RETRIVA_SEARCH_ALL === true }) }),
};

async function streamMessage(chatId, content, signal) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
    body: JSON.stringify({ content, search_all: window.RETRIVA_SEARCH_ALL === true }),
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return res.body.getReader();
}

// change password from the account menu
const _cpBtn = document.getElementById("change-pw-btn");
if (_cpBtn) _cpBtn.addEventListener("click", async () => {
  const current = prompt("Current password:");
  if (!current) return;
  const next = prompt("New password (at least 8 characters):");
  if (!next) return;
  try {
    await apiRequest("/api/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
    alert("Password changed.");
  } catch (err) { alert(err.message); }
});

// export all my data as a JSON file
const _exBtn = document.getElementById("export-data-btn");
if (_exBtn) _exBtn.addEventListener("click", async () => {
  try {
    const data = await apiRequest("/api/auth/export");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    a.download = "retriva-my-data.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  } catch (err) { alert(err.message); }
});

// permanently delete my account and everything in it
const _delBtn = document.getElementById("delete-account-btn");
if (_delBtn) _delBtn.addEventListener("click", async () => {
  if (!confirm("Delete your account?\n\nThis permanently removes all your knowledge bases, documents and chats. It cannot be undone.\n\nTip: use Export my data first.")) return;
  const password = prompt("Type your password to confirm:");
  if (!password) return;
  try {
    await apiRequest("/api/auth/delete-account", { method: "POST", body: JSON.stringify({ password }) });
    clearToken();
    localStorage.removeItem("retriva_user");
    alert("Your account has been deleted.");
    window.location.href = "index.html";
  } catch (err) { alert(err.message); }
});

// replaces the browser's blocking alert() with a toast
window.alert = function (message) {
  let box = document.getElementById("toast-box");
  if (!box) {
    box = document.createElement("div");
    box.id = "toast-box";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = String(message);
  box.appendChild(t);
  setTimeout(() => t.remove(), 5000);
  t.addEventListener("click", () => t.remove());
};