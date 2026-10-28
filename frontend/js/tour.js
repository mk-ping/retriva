// first-time walkthrough: opens once per account on the dashboard, replayable from the account menu
(function () {
  const STEPS = [
    { title: "Welcome to Retriva", text: "Retriva answers questions using only your own documents, and shows the exact passage behind every answer. Here is how to get going in four short steps." },
    { title: "1. Add your documents", text: "Drop PDF, Word, PowerPoint, Excel, HTML, text or CSV files, or add a web page by address. Scanned PDFs are read with OCR. You do not need to name anything first: a knowledge base is created for you and you can rename it later." },
    { title: "2. Wait for the green dot", text: "Each document is read and indexed first. A pulsing yellow dot means it is still processing, green means ready, and red means something went wrong. The reason is shown under the file name." },
    { title: "3. Ask questions", text: "Ask in plain language. Follow-up questions work too. Click a suggested question to start, or tick All knowledge bases to search everything you have uploaded." },
    { title: "4. Check the sources", text: "The green [1] markers in an answer point to the passages it used. Click one to read the passage and open the original file at that page. The percentage shows how closely a passage matches your question. It is a search score, not a guarantee that the answer is right." },
  ];

  function key() {
    const u = typeof getStoredUser === "function" ? getStoredUser() : null;
    return "retriva_tour_" + (u ? u.id : "guest");
  }
  function markDone() { try { localStorage.setItem(key(), "1"); } catch (e) { /* storage blocked */ } }

  function startTour() {
    let i = 0;
    const overlay = document.createElement("div");
    overlay.className = "ui-overlay";
    const box = document.createElement("div");
    box.className = "ui-dialog";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function close() { document.removeEventListener("keydown", onKey, true); overlay.remove(); markDone(); }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey, true);

    function render() {
      box.textContent = "";
      const step = document.createElement("div");
      step.className = "ui-step";
      step.textContent = (i + 1) + " of " + STEPS.length;
      const title = document.createElement("div");
      title.className = "ui-title";
      title.textContent = STEPS[i].title;
      const text = document.createElement("div");
      text.className = "ui-msg";
      text.textContent = STEPS[i].text;
      const row = document.createElement("div");
      row.className = "ui-actions";

      const skip = document.createElement("button");
      skip.className = "btn ui-skip";
      skip.textContent = "Skip tour";
      skip.addEventListener("click", close);
      row.appendChild(skip);

      if (i > 0) {
        const back = document.createElement("button");
        back.className = "btn btn-secondary";
        back.textContent = "Back";
        back.addEventListener("click", () => { i--; render(); });
        row.appendChild(back);
      }
      const next = document.createElement("button");
      next.className = "btn btn-primary";
      next.textContent = i === STEPS.length - 1 ? "Done" : "Next";
      next.addEventListener("click", () => { if (i === STEPS.length - 1) close(); else { i++; render(); } });
      row.appendChild(next);

      box.append(step, title, text, row);
      next.focus();
    }
    render();
  }

  window.startTour = startTour;

  const btn = document.getElementById("tour-btn");
  if (btn) btn.addEventListener("click", () => {
    const menu = document.getElementById("account-menu");
    if (menu) menu.classList.remove("open");
    startTour();
  });

  if (document.getElementById("kb-list")) {
    let done = false;
    try { done = localStorage.getItem(key()) === "1"; } catch (e) { /* ignore */ }
    if (!done) setTimeout(startTour, 700);
  }
})();