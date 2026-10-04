// styled replacements for confirm() and prompt(); both return promises, so callers use await
function _uiDialog(message, withInput, defaultValue) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "ui-overlay";
    const box = document.createElement("div");
    box.className = "ui-dialog";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    const msg = document.createElement("div");
    msg.className = "ui-msg";
    msg.textContent = message;          // textContent only, never HTML
    box.appendChild(msg);

    let input = null;
    if (withInput) {
      input = document.createElement("input");
      input.className = "ui-input";
      input.type = /password/i.test(message) ? "password" : "text";
      input.value = defaultValue || "";
      box.appendChild(input);
    }

    const row = document.createElement("div");
    row.className = "ui-actions";
    const cancel = document.createElement("button");
    cancel.className = "btn btn-secondary";
    cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.className = "btn btn-primary";
    ok.textContent = "OK";
    row.appendChild(cancel);
    row.appendChild(ok);
    box.appendChild(row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    const close = (value) => {
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      if (prev && prev.focus) prev.focus();
      resolve(value);
    };
    const accept = () => close(withInput ? input.value : true);
    const reject = () => close(withInput ? null : false);
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); reject(); }
      if (e.key === "Enter" && e.target !== cancel) { e.preventDefault(); accept(); }
    };
    document.addEventListener("keydown", onKey, true);
    ok.addEventListener("click", accept);
    cancel.addEventListener("click", reject);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) reject(); });
    (input || ok).focus();
    if (input) input.select();
  });
}
function uiConfirm(message) { return _uiDialog(message, false); }
function uiPrompt(message, defaultValue) { return _uiDialog(message, true, defaultValue); }