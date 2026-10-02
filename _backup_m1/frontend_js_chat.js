const params = new URLSearchParams(window.location.search);
const kbId = params.get("kb");

let currentKB = null;
let currentChatId = null;
let allChats = [];
let pollTimer = null;
let lastUserMessage = null;
let activeAbortController = null;

if (!kbId) {
  window.location.href = "dashboard.html";
}

function initials(name) {
  return name.trim().split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderMarkdown(text) {
  const rawHtml = marked.parse(text, { breaks: true });
  return DOMPurify.sanitize(rawHtml);
}

// account corner menu
function renderAccount() {
  const user = getStoredUser();
  if (!user) { window.location.href = "auth.html"; return; }
  document.getElementById("account-avatar").textContent = initials(user.name);
  document.getElementById("account-name").textContent = user.name;
  document.getElementById("account-email").textContent = user.email;
}

document.getElementById("account-btn").addEventListener("click", () => {
  document.getElementById("account-menu").classList.toggle("open");
});
document.addEventListener("click", (e) => {
  const menu = document.getElementById("account-menu");
  const btn = document.getElementById("account-btn");
  if (!menu.contains(e.target) && !btn.contains(e.target)) menu.classList.remove("open");
});
document.getElementById("sign-out-btn").addEventListener("click", () => {
  clearToken();
  localStorage.removeItem("retriva_user");
  window.location.href = "index.html";
});

// sidebar collapse toggle
document.getElementById("sidebar-toggle-btn").addEventListener("click", () => {
  document.getElementById("main-sidebar").classList.toggle("collapsed");
});

// chat search inside this KB's sidebar
const searchInput = document.getElementById("chat-search-input");
let searchDebounce = null;

searchInput.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  const q = searchInput.value.trim();
  if (!q) { renderChatList(); return; }
  searchDebounce = setTimeout(() => runSearch(q), 300);
});

async function runSearch(q) {
  try {
    const results = await api.searchChats(q);
    const list = document.getElementById("chat-list");
    const matchesThisKB = results.filter(c => c.knowledge_base_id === kbId);
    if (!matchesThisKB.length) {
      list.innerHTML = `<div class="empty-chat-list-note">No chats match "${escapeHtml(q)}".</div>`;
      return;
    }
    list.innerHTML = matchesThisKB.map(c => `
      <div class="chat-list-item" data-chat-id="${c.id}">
        <span class="chat-list-item-title">${escapeHtml(c.title)}</span>
      </div>
    `).join("");
    list.querySelectorAll(".chat-list-item").forEach(el => {
      el.addEventListener("click", () => openChat(el.dataset.chatId));
    });
  } catch (err) {
    alert(err.message);
  }
}

// KB details + documents
async function loadKBDetails() {
  try {
    currentKB = await api.getKB(kbId);
    document.getElementById("kb-name").textContent = currentKB.name;
    document.getElementById("kb-desc").textContent = currentKB.description || "";
    renderDocList(currentKB.documents || []);

    const stillProcessing = (currentKB.documents || []).some(d => d.status === "processing");
    if (stillProcessing && !pollTimer) pollTimer = setInterval(loadKBDetails, 3000);
    else if (!stillProcessing && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  } catch (err) {
    document.getElementById("kb-name").textContent = "Not found";
  }
}

function renderDocList(docs) {
  const list = document.getElementById("doc-list");
  if (!docs.length) {
    list.innerHTML = `<div class="empty-doc-note">No documents yet. Upload one above.</div>`;
    return;
  }
  list.innerHTML = docs.map(d => `
    <div class="doc-item">
      <div class="doc-status-dot ${d.status}" title="${d.status}"></div>
      <div class="doc-item-text">
        <div class="doc-item-name">${escapeHtml(d.filename)}</div>
        <div class="doc-item-meta">${d.status === "ready" ? d.chunk_count + " chunks" : d.status === "failed" ? escapeHtml(d.error_message || "Failed") : "Processing..."}</div>
      </div>
      <button class="doc-reprocess" data-doc-id="${d.id}" title="Reprocess">&#8635;</button>
      <button class="doc-delete" data-doc-id="${d.id}" title="Delete">&times;</button>
    </div>
  `).join("");

  list.querySelectorAll(".doc-reprocess").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      try { await api.reprocessDocument(kbId, btn.dataset.docId); loadKBDetails(); }
      catch (err) { alert(err.message); }
    });
  });

  list.querySelectorAll(".doc-delete").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this document?")) return;
      try { await api.deleteDocument(kbId, btn.dataset.docId); loadKBDetails(); }
      catch (err) { alert(err.message); }
    });
  });
}

// upload
const uploadZone = document.getElementById("upload-zone");
const fileInput = document.getElementById("file-input");

async function handleFiles(files) {
  for (const file of Array.from(files)) {
    try {
      await api.uploadDocument(kbId, file);
      loadKBDetails();
    } catch (err) {
      if (err.message.includes("matches an existing document")) {
        const proceed = confirm(`${err.message}\n\nUpload it anyway as a duplicate?`);
        if (proceed) {
          try {
            await api.uploadDocument(kbId, file, true);
            loadKBDetails();
          } catch (err2) {
            alert(`${file.name}: ${err2.message}`);
          }
        }
      } else {
        alert(`${file.name}: ${err.message}`);
      }
    }
  }
}

fileInput.addEventListener("change", () => { handleFiles(fileInput.files); fileInput.value = ""; });
uploadZone.addEventListener("dragover", (e) => { e.preventDefault(); uploadZone.classList.add("drag-over"); });
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("drag-over"));
uploadZone.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadZone.classList.remove("drag-over");
  handleFiles(e.dataTransfer.files);
});

// chat list for this KB
async function loadChatList() {
  try {
    allChats = await api.listChats(kbId);
    renderChatList();
  } catch (err) {
    document.getElementById("chat-list").innerHTML = `<div class="empty-chat-list-note">${err.message}</div>`;
  }
}

function renderChatList() {
  const list = document.getElementById("chat-list");
  if (!allChats.length) {
    list.innerHTML = `<div class="empty-chat-list-note">No chats yet.</div>`;
    return;
  }
  list.innerHTML = allChats.map(c => `
    <div class="chat-list-item ${c.id === currentChatId ? "active" : ""}" data-chat-id="${c.id}">
      <span class="chat-list-item-title" data-chat-id="${c.id}">${escapeHtml(c.title)}</span>
      <button class="chat-delete" data-chat-id="${c.id}" title="Delete chat">&times;</button>
    </div>
  `).join("");

  list.querySelectorAll(".chat-list-item").forEach(el => {
    el.addEventListener("click", (e) => {
      if (e.target.classList.contains("chat-delete") || e.target.tagName === "INPUT") return;
      openChat(el.dataset.chatId);
    });
  });

  list.querySelectorAll(".chat-list-item-title").forEach(el => {
    el.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      startRename(el.dataset.chatId, el);
    });
  });

  list.querySelectorAll(".chat-delete").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this chat?")) return;
      try {
        await api.deleteChat(btn.dataset.chatId);
        if (currentChatId === btn.dataset.chatId) startNewChat();
        loadChatList();
      } catch (err) { alert(err.message); }
    });
  });
}

function startRename(chatId, titleEl) {
  const currentTitle = titleEl.textContent;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "chat-list-item-title-input";
  input.value = currentTitle;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  const commit = async () => {
    const newTitle = input.value.trim() || currentTitle;
    try {
      await api.renameChat(chatId, newTitle);
      if (chatId === currentChatId) document.getElementById("chat-title-label").textContent = newTitle;
      loadChatList();
    } catch (err) {
      alert(err.message);
      loadChatList();
    }
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") input.blur();
    if (e.key === "Escape") { input.value = currentTitle; input.blur(); }
  });
  input.addEventListener("blur", commit, { once: true });
}

async function openChat(chatId) {
  try {
    const chat = await api.getChat(chatId);
    currentChatId = chat.id;
    document.getElementById("chat-title-label").textContent = chat.title;
    renderChatList();

    const messages = document.getElementById("messages");
    messages.innerHTML = "";
    if (!chat.messages.length) {
      messages.innerHTML = `<div class="chat-empty"><h3>No messages yet</h3><p>Ask your first question below.</p></div>`;
    } else {
      chat.messages.forEach(m => {
        appendMessage(m.role, m.content, m.sources || [], m.id, m.feedback);
        if (m.role === "user") lastUserMessage = m.content;
      });
    }
  } catch (err) {
    alert(err.message);
  }
}

function startNewChat() {
  currentChatId = null;
  lastUserMessage = null;
  document.getElementById("chat-title-label").textContent = "";
  renderChatList();
  document.getElementById("messages").innerHTML = `
    <div class="chat-empty">
      <h3>Ask something about this knowledge base</h3>
      <p>Upload a document on the left, then ask a question here. Every answer will show exactly which source it came from.</p>
    </div>
  `;
}

document.getElementById("new-chat-btn").addEventListener("click", startNewChat);

// messages
function removeEmptyChat() {
  const el = document.querySelector(".chat-empty");
  if (el) el.remove();
}

function appendMessage(role, content, sources = [], messageId = null, feedback = null) {
  removeEmptyChat();
  const messages = document.getElementById("messages");
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = renderMarkdown(content);
  row.appendChild(bubble);

  if (role === "assistant" && sources.length) {
    const srcWrap = document.createElement("div");
    srcWrap.className = "msg-sources";
    sources.forEach(s => {
      const chip = document.createElement("div");
      chip.className = "source-chip";
      chip.innerHTML = `${escapeHtml(s.filename)} <span class="source-chip-score">${Math.round(s.score * 100)}%</span>`;
      chip.addEventListener("click", () => showSourceDetail(s));
      srcWrap.appendChild(chip);
    });
    bubble.appendChild(srcWrap);
  }

  if (role === "assistant") {
    const actions = document.createElement("div");
    actions.className = "msg-actions";

    const copyBtn = document.createElement("button");
    copyBtn.className = "msg-action-btn";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(content);
      copyBtn.textContent = "Copied";
      copyBtn.classList.add("copied");
      setTimeout(() => { copyBtn.textContent = "Copy"; copyBtn.classList.remove("copied"); }, 1500);
    });
    actions.appendChild(copyBtn);

    if (lastUserMessage) {
      const regenBtn = document.createElement("button");
      regenBtn.className = "msg-action-btn";
      regenBtn.textContent = "Regenerate";
      regenBtn.addEventListener("click", () => regenerateLast(row));
      actions.appendChild(regenBtn);
    }

    if (messageId) {
      const up = document.createElement("button");
      up.className = "feedback-btn" + (feedback === "up" ? " active-up" : "");
      up.innerHTML = "<svg viewBox=\"0 0 20 20\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"><path d=\"M7 10v7H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1h3zm0 0l3.5-6a1.5 1.5 0 0 1 2.8 1l-1 3.5H16a1.5 1.5 0 0 1 1.4 2l-1.7 5A2 2 0 0 1 13.8 17H7\"/></svg>";

      const down = document.createElement("button");
      down.className = "feedback-btn" + (feedback === "down" ? " active-down" : "");
      down.innerHTML = "<svg viewBox=\"0 0 20 20\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\"><path d=\"M13 10V3h3a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-3zm0 0l-3.5 6a1.5 1.5 0 0 1-2.8-1l1-3.5H4a1.5 1.5 0 0 1-1.4-2l1.7-5A2 2 0 0 1 6.2 3H13\"/></svg>";

      up.addEventListener("click", () => toggleFeedback(messageId, "up", up, down));
      down.addEventListener("click", () => toggleFeedback(messageId, "down", up, down));

      actions.appendChild(up);
      actions.appendChild(down);
    }

    bubble.appendChild(actions);
  }

  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
  return row;
}

async function toggleFeedback(messageId, value, upBtn, downBtn) {
  const isActive = (value === "up" && upBtn.classList.contains("active-up")) || (value === "down" && downBtn.classList.contains("active-down"));
  const newValue = isActive ? "none" : value;
  try {
    await api.setFeedback(currentChatId, messageId, newValue);
    upBtn.classList.remove("active-up");
    downBtn.classList.remove("active-down");
    if (newValue === "up") upBtn.classList.add("active-up");
    if (newValue === "down") downBtn.classList.add("active-down");
  } catch (err) {
    alert(err.message);
  }
}

function appendTyping() {
  removeEmptyChat();
  const messages = document.getElementById("messages");
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.innerHTML = `<div class="msg-bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>`;
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
  return row;
}

async function regenerateLast(oldRow) {
  if (!lastUserMessage || !currentChatId) return;
  oldRow.remove();
  const typingRow = appendTyping();
  try {
    const response = await api.sendMessage(currentChatId, lastUserMessage);
    typingRow.remove();
    appendMessage("assistant", response.content, response.sources || [], response.id, response.feedback);
    loadChatList();
  } catch (err) {
    typingRow.remove();
    appendMessage("assistant", `Something went wrong: ${err.message}`);
  }
}

function showSourceDetail(source) {
  const panel = document.getElementById("sources-panel");
  const body = document.getElementById("sources-panel-body");
  body.innerHTML = `
    <div class="source-detail">
      <div class="source-detail-file">${escapeHtml(source.filename)}</div>
      <div class="source-detail-score">${Math.round(source.score * 100)}% match</div>
      <div class="source-detail-text">${escapeHtml(source.chunk_text)}</div>
    </div>
  `;
  panel.classList.add("open");
}

document.getElementById("sources-panel-close").addEventListener("click", () => {
  document.getElementById("sources-panel").classList.remove("open");
});

async function ensureChat() {
  if (currentChatId) return currentChatId;
  const chat = await api.createChat(kbId, "New chat");
  currentChatId = chat.id;
  await loadChatList();
  return currentChatId;
}

const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");

async function sendMessage() {
  const content = chatInput.value.trim();
  if (!content) return;

  chatInput.value = "";
  chatInput.style.height = "auto";
  sendBtn.disabled = true;
  sendBtn.style.display = "none";
  document.getElementById("stop-btn").classList.add("visible");

  appendMessage("user", content);
  lastUserMessage = content;

  removeEmptyChat();
  const messages = document.getElementById("messages");
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div>`;
  row.appendChild(bubble);
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;

  activeAbortController = new AbortController();
  let fullText = "";
  let firstToken = true;

  try {
    const chatId = await ensureChat();
    const reader = await streamMessage(chatId, content, activeAbortController.signal);
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = JSON.parse(line.slice(6));

        if (data.token) {
          if (firstToken) { bubble.innerHTML = ""; firstToken = false; }
          fullText += data.token;
          bubble.innerHTML = renderMarkdown(fullText);
          messages.scrollTop = messages.scrollHeight;
        }
        if (data.error) {
          bubble.innerHTML = renderMarkdown(`Something went wrong: ${data.error}`);
        }
        if (data.done) {
          row.remove();
          appendMessage("assistant", fullText, data.sources || [], data.message_id, null);
          loadChatList();
        }
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      row.remove();
      if (fullText) appendMessage("assistant", fullText + " *(stopped)*", [], null, null);
    } else {
      bubble.innerHTML = renderMarkdown(`Something went wrong: ${err.message}`);
    }
  } finally {
    sendBtn.disabled = false;
    sendBtn.style.display = "flex";
    document.getElementById("stop-btn").classList.remove("visible");
    activeAbortController = null;
    chatInput.focus();
  }
}

document.getElementById("stop-btn").addEventListener("click", () => {
  if (activeAbortController) activeAbortController.abort();
});

sendBtn.addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
chatInput.addEventListener("input", function () {
  this.style.height = "auto";
  this.style.height = Math.min(this.scrollHeight, 140) + "px";
});

// debug retrieval inspector
document.getElementById("inspector-toggle-btn").addEventListener("click", () => {
  document.getElementById("inspector-panel").classList.toggle("open");
});

document.getElementById("inspector-run-btn").addEventListener("click", runInspector);
document.getElementById("inspector-query-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runInspector();
});

async function runInspector() {
  const q = document.getElementById("inspector-query-input").value.trim();
  if (!q) return;
  const resultsEl = document.getElementById("inspector-results");
  resultsEl.innerHTML = `<div class="empty-doc-note">Running retrieval...</div>`;

  try {
    const data = await api.debugRetrieve(kbId, q);
    if (!data.chunks.length) {
      resultsEl.innerHTML = `<div class="empty-doc-note">No chunks retrieved — the knowledge base may be empty or nothing matched closely enough.</div>`;
      return;
    }
    resultsEl.innerHTML = data.chunks.map((c, i) => `
      <div class="inspector-chunk">
        <div class="inspector-chunk-head">
          <span>#${i + 1} — ${escapeHtml(c.filename)}</span>
          <span class="inspector-chunk-score">${Math.round(c.score * 100)}% match</span>
        </div>
        <div class="inspector-chunk-text">${escapeHtml(c.text)}</div>
      </div>
    `).join("");
  } catch (err) {
    resultsEl.innerHTML = `<div class="empty-doc-note">${err.message}</div>`;
  }
}

// init
renderAccount();
loadKBDetails();
loadChatList();

const targetChatId = params.get("chat");
if (targetChatId) {
  setTimeout(() => openChat(targetChatId), 500);
}
