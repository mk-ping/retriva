function switchTab(tab) {
  document.getElementById("tab-login").classList.toggle("active", tab === "login");
  document.getElementById("tab-signup").classList.toggle("active", tab === "signup");
  document.getElementById("form-login").classList.toggle("active", tab === "login");
  document.getElementById("form-signup").classList.toggle("active", tab === "signup");
  hideAlert();
}

function showAlert(message) {
  const el = document.getElementById("auth-alert");
  el.textContent = message;
  el.classList.add("visible");
}

function hideAlert() {
  const el = document.getElementById("auth-alert");
  el.classList.remove("visible");
}

function setSubmitting(buttonId, isSubmitting, defaultText) {
  const btn = document.getElementById(buttonId);
  btn.disabled = isSubmitting;
  btn.textContent = isSubmitting ? "Please wait..." : defaultText;
}

function onAuthSuccess(data) {
  setToken(data.access_token);
  setStoredUser(data.user);
  window.location.href = "dashboard.html";
}

document.getElementById("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideAlert();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;

  setSubmitting("login-submit", true);
  try {
    const data = await api.login(email, password);
    onAuthSuccess(data);
  } catch (err) {
    showAlert(err.message);
    setSubmitting("login-submit", false, "Sign in");
  }
});

document.getElementById("form-signup").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideAlert();

  const name = document.getElementById("signup-name").value.trim();
  const email = document.getElementById("signup-email").value.trim();
  const password = document.getElementById("signup-password").value;

  let valid = true;
  const nameErr = document.getElementById("signup-name-err");
  const pwErr = document.getElementById("signup-password-err");

  if (name.length < 2) { nameErr.classList.add("visible"); valid = false; }
  else { nameErr.classList.remove("visible"); }

  if (password.length < 8) { pwErr.classList.add("visible"); valid = false; }
  else { pwErr.classList.remove("visible"); }

  if (!valid) return;

  setSubmitting("signup-submit", true);
  try {
    const data = await api.signup(name, email, password);
    onAuthSuccess(data);
  } catch (err) {
    showAlert(err.message);
    setSubmitting("signup-submit", false, "Create account");
  }
});

// If already logged in, skip straight to dashboard
if (getToken()) {
  window.location.href = "dashboard.html";
}
