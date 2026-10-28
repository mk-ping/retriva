const resetToken = new URLSearchParams(window.location.search).get("t");
if (resetToken) history.replaceState(null, "", "reset.html");   // keep the secret out of the address bar

const msg = document.getElementById("msg");
const formRequest = document.getElementById("form-request");
const formReset = document.getElementById("form-reset");

function show(text, ok) {
  msg.textContent = text;
  msg.className = "auth-alert visible" + (ok ? " ok" : "");
}

if (resetToken) {
  formRequest.classList.remove("active");
  formReset.classList.add("active");
}

formRequest.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("request-submit");
  btn.disabled = true;
  try {
    const data = await apiRequest("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email: document.getElementById("email").value.trim() }),
    });
    show(data.message, true);
  } catch (err) {
    show(err.message, false);
    btn.disabled = false;
  }
});

formReset.addEventListener("submit", async (e) => {
  e.preventDefault();
  const pw = document.getElementById("pw").value;
  if (pw.length < 8) { show("Password must be at least 8 characters.", false); return; }
  if (pw !== document.getElementById("pw2").value) { show("The two passwords do not match.", false); return; }
  const btn = document.getElementById("reset-submit");
  btn.disabled = true;
  try {
    await apiRequest("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token: resetToken, new_password: pw }),
    });
    show("Password changed. Taking you to sign in...", true);
    setTimeout(() => { window.location.href = "auth.html"; }, 1800);
  } catch (err) {
    show(err.message, false);
    btn.disabled = false;
  }
});