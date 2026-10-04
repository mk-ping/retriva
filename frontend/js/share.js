const token = new URLSearchParams(window.location.search).get("t");
const API = window.RETRIVA_API || "http://localhost:8000";
const log = document.getElementById("log");
const qInput = document.getElementById("q");
const sendBtn = document.getElementById("send");

function bubble(cls) {
  const d = document.createElement("div");
  d.className = "b " + cls;
  log.appendChild(d);
  d.scrollIntoView({ block: "end" });
  return d;
}

async function call(path, options) {
  const res = await fetch(API + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed (" + res.status + ")");
  return data;
}

(async function () {
  if (!token) { document.getElementById("title").textContent = "Invalid link"; return; }
  try {
    const info = await call("/api/share/public/" + encodeURIComponent(token));
    document.getElementById("title").textContent = info.name;
    document.getElementById("desc").textContent = info.description;
    document.title = "Retriva - " + info.name;
  } catch (err) {
    document.getElementById("title").textContent = err.message;
    document.getElementById("form").style.display = "none";
  }
})();

document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  if (!q || !token) return;
  qInput.value = "";
  sendBtn.disabled = true;
  bubble("user").textContent = q;
  const out = bubble("bot");
  out.textContent = "Thinking...";
  try {
    const data = await call("/api/share/public/" + encodeURIComponent(token) + "/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    out.innerHTML = DOMPurify.sanitize(marked.parse(data.answer, { breaks: true }));
    if (data.sources.length) {
      const det = document.createElement("details");
      const sum = document.createElement("summary");
      sum.textContent = data.sources.length + " source passage(s)";
      det.appendChild(sum);
      data.sources.forEach((s, i) => {
        const l = document.createElement("div");
        l.className = "src-l";
        l.textContent = "[" + (i + 1) + "] " + s.filename + (s.page ? " p." + s.page : "") + " - " + Math.round(s.score * 100) + "%";
        const t = document.createElement("div");
        t.className = "src-t";
        t.textContent = s.chunk_text;   // textContent only, so document text can never run as HTML
        det.appendChild(l);
        det.appendChild(t);
      });
      out.appendChild(det);
    }
  } catch (err) {
    out.textContent = err.message;
  } finally {
    sendBtn.disabled = false;
    qInput.focus();
    out.scrollIntoView({ block: "end" });
  }
});