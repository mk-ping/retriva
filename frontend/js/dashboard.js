let currentKBs = [];
let activeKBId = null;

function initials(name) {
  return name.trim().split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderAccount() {
  const user = getStoredUser();
  if (!user) {
    window.location.href = "auth.html";
    return;
  }
  document.getElementById("account-avatar").textContent = initials(user.name);
  document.getElementById("account-name").textContent = user.name;
  document.getElementById("account-email").textContent = user.email;
}

function toggleAccountMenu() {
  document.getElementById("account-menu").classList.toggle("open");
}

document.addEventListener("click", (e) => {
  const menu = document.getElementById("account-menu");
  const btn = document.getElementById("account-btn");
  if (!menu.contains(e.target) && !btn.contains(e.target)) {
    menu.classList.remove("open");
  }
});

document.getElementById("account-btn").addEventListener("click", toggleAccountMenu);

document.getElementById("sign-out-btn").addEventListener("click", () => {
  clearToken();
  localStorage.removeItem("retriva_user");
  window.location.href = "index.html";
});

function renderKBList() {
  const list = document.getElementById("kb-list");
  if (!currentKBs.length) {
    list.innerHTML = `<div class="empty-kb-note">No knowledge bases yet. Create one to get started.</div>`;
    return;
  }
  list.innerHTML = currentKBs.map(kb => `
    <div class="kb-item ${kb.id === activeKBId ? "active" : ""}" data-kb-id="${kb.id}">
      <div class="kb-icon">${kb.name.slice(0, 2).toUpperCase()}</div>
      <div class="kb-item-text">
        <div class="kb-item-name">${escapeHtml(kb.name)}</div>
        <div class="kb-item-meta">${kb.document_count} document${kb.document_count === 1 ? "" : "s"}</div>
      </div>
    </div>
  `).join("");

  list.querySelectorAll(".kb-item").forEach(el => {
    el.addEventListener("click", () => selectKB(el.dataset.kbId));
  });
}

async function loadKBs() {
  try {
    currentKBs = await api.listKBs();
    renderKBList();
  } catch (err) {
    document.getElementById("kb-list").innerHTML = `<div class="empty-kb-note">Failed to load: ${err.message}</div>`;
  }
}

function selectKB(kbId) {
  activeKBId = kbId;
  renderKBList();
  window.location.href = `chat.html?kb=${kbId}`;
}

const modal = document.getElementById("new-kb-modal");

document.getElementById("new-kb-btn").addEventListener("click", () => {
  document.getElementById("kb-name-input").value = "";
  document.getElementById("kb-desc-input").value = "";
  modal.classList.add("open");
  document.getElementById("kb-name-input").focus();
});

document.getElementById("kb-modal-cancel").addEventListener("click", () => {
  modal.classList.remove("open");
});

modal.addEventListener("click", (e) => {
  if (e.target === modal) modal.classList.remove("open");
});

document.getElementById("kb-modal-create").addEventListener("click", async () => {
  const name = document.getElementById("kb-name-input").value.trim();
  const description = document.getElementById("kb-desc-input").value.trim();
  if (!name) return;

  const btn = document.getElementById("kb-modal-create");
  btn.disabled = true;
  btn.textContent = "Creating...";

  try {
    const kb = await api.createKB(name, description);
    modal.classList.remove("open");
    await loadKBs();
    selectKB(kb.id);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Create";
  }
});

const searchInput = document.getElementById("chat-search-input");
let searchDebounce = null;

searchInput.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  const q = searchInput.value.trim();
  if (!q) { renderKBList(); return; }
  searchDebounce = setTimeout(() => runSearch(q), 300);
});

async function runSearch(q) {
  try {
    const results = await api.searchChats(q);
    const list = document.getElementById("kb-list");
    if (!results.length) {
      list.innerHTML = `<div class="empty-kb-note">No chats match "${escapeHtml(q)}".</div>`;
      return;
    }
    list.innerHTML = results.map(c => `<div class="search-result-item" data-chat-id="${c.id}" data-kb-id="${c.knowledge_base_id}">
      <div class="search-result-title">${escapeHtml(c.title)}</div>
    </div>`).join("");
    list.querySelectorAll(".search-result-item").forEach(el => {
      el.addEventListener("click", () => {
        window.location.href = `chat.html?kb=${el.dataset.kbId}&chat=${el.dataset.chatId}`;
      });
    });
  } catch (err) {
    alert(err.message);
  }
}

renderAccount();
loadKBs();
