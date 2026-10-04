function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;   // textContent only, so document text can never run as HTML
  return e;
}

(async function () {
  if (!getToken()) { window.location.href = "auth.html"; return; }
  const list = document.getElementById("list");
  try {
    const items = await apiRequest("/api/chats/feedback/downvoted");
    if (!items.length) { list.appendChild(el("p", "", "No downvoted answers yet.")); return; }
    items.forEach(it => {
      const card = el("div", "fb-card");
      card.appendChild(el("div", "fb-label", "Question"));
      card.appendChild(el("div", "fb-text", it.question || "(not found)"));
      card.appendChild(el("div", "fb-label", "Answer"));
      card.appendChild(el("div", "fb-text", it.answer));

      const d = el("details");
      d.appendChild(el("summary", "", it.sources.length + " retrieved passage(s)"));
      it.sources.forEach((s, i) => {
        d.appendChild(el("div", "fb-label", "[" + (i + 1) + "] " + s.filename + (s.page ? " p." + s.page : "") + " - " + Math.round(s.score * 100) + "%"));
        d.appendChild(el("div", "fb-chunk", s.chunk_text));
      });
      if (it.sources.length) card.appendChild(d);

      const a = el("a", "fb-open", "Open this chat");
      a.href = "chat.html?kb=" + encodeURIComponent(it.knowledge_base_id) + "&chat=" + encodeURIComponent(it.chat_id);
      card.appendChild(a);
      list.appendChild(card);
    });
  } catch (err) {
    list.appendChild(el("p", "", err.message));
  }
})();