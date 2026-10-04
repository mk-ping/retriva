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
    fillQuickTarget();
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
  const name = document.getElementById("kb-name-input").value.trim() || "Untitled knowledge base";
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


// ---- quick upload: drop files first, the knowledge base is created or chosen for you ----
function fillQuickTarget() {
  const sel = document.getElementById("quick-target");
  if (!sel) return;
  const keep = sel.value;
  sel.innerHTML = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = "New knowledge base (named after your file)";
  sel.appendChild(first);
  currentKBs.forEach(kb => {
    const o = document.createElement("option");
    o.value = kb.id;
    o.textContent = "Add to: " + kb.name;   // textContent, so names can never run as HTML
    sel.appendChild(o);
  });
  if (keep && currentKBs.some(k => k.id === keep)) sel.value = keep;
}

async function quickUpload(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;
  const zone = document.getElementById("quick-upload");
  const title = zone.querySelector(".quick-title");
  const original = title.textContent;
  zone.classList.add("busy");
  title.textContent = "Uploading " + files.length + " file" + (files.length === 1 ? "" : "s") + "...";
  try {
    let targetId = document.getElementById("quick-target").value;
    if (!targetId) {
      const base = files[0].name.replace(/\.[^.]+$/, "").trim().slice(0, 50) || "Untitled";
      const name = files.length > 1 ? base + " +" + (files.length - 1) + " more" : base;
      targetId = (await api.createKB(name, "")).id;
    }
    const failed = [];
    for (const f of files) {
      try { await api.uploadDocument(targetId, f); }
      catch (err) { failed.push(f.name + ": " + err.message); }
    }
    if (failed.length) {
      alert(failed.join("\n"));
      await new Promise(r => setTimeout(r, 3000));   // let the message be read before leaving
    }
    window.location.href = "chat.html?kb=" + targetId;
  } catch (err) {
    alert(err.message);
    zone.classList.remove("busy");
    title.textContent = original;
  }
}

const _qz = document.getElementById("quick-upload");
const _qi = document.getElementById("quick-file-input");
_qi.addEventListener("change", () => { quickUpload(_qi.files); _qi.value = ""; });
_qz.addEventListener("dragover", (e) => { e.preventDefault(); _qz.classList.add("drag-over"); });
_qz.addEventListener("dragleave", () => _qz.classList.remove("drag-over"));
_qz.addEventListener("drop", (e) => { e.preventDefault(); _qz.classList.remove("drag-over"); quickUpload(e.dataTransfer.files); });