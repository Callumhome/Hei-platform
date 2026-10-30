(() => {
  const forgotForm = document.getElementById("forgot-form");
  const resetForm = document.getElementById("reset-form");
  const notice = document.getElementById("notice");
  const successPanel = document.getElementById("success-panel");
  const title = document.getElementById("page-title");
  const intro = document.getElementById("page-intro");
  const backLink = document.getElementById("back-link");
  const successTitle = document.getElementById("success-title");
  const successCopy = document.getElementById("success-copy");
  const resetToken = new URLSearchParams(window.location.search).get("token");

  function showNotice(message, isError = false) {
    notice.textContent = message;
    notice.classList.toggle("error", isError);
    notice.hidden = false;
  }

  function showSuccess(heading, message) {
    forgotForm.hidden = true;
    resetForm.hidden = true;
    notice.hidden = true;
    successTitle.textContent = heading;
    successCopy.textContent = message;
    successPanel.hidden = false;
  }

  async function postJson(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    let body = {};
    try { body = await response.json(); } catch (_) { /* use generic error below */ }
    if (!response.ok) {
      const error = new Error(body.detail || "Something went wrong. Please try again.");
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function setBusy(button, busy, label) {
    button.disabled = busy;
    button.textContent = busy ? "Please wait…" : label;
  }

  if (resetToken) {
    forgotForm.hidden = true;
    resetForm.hidden = false;
    title.textContent = "Choose a new password";
    intro.textContent = "Create a new password for your Home Energy Intelligence account.";
    backLink.textContent = "← Back to sign in";
  }

  forgotForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    notice.hidden = true;
    const email = document.getElementById("email").value.trim();
    if (!email || !document.getElementById("email").checkValidity()) {
      showNotice("Enter a valid email address to continue.", true);
      return;
    }
    const button = document.getElementById("forgot-submit");
    setBusy(button, true, "Send reset link →");
    try {
      await postJson("/api/v1/auth/forgot-password", { email });
      showSuccess("Check your inbox", "If an active verified account exists for that address, reset instructions will arrive shortly. You can safely close this page.");
    } catch (error) {
      showNotice(error.status === 429
        ? "Too many reset requests. Please wait before trying again."
        : "We couldn't process that request just now. Please try again shortly.", true);
    } finally {
      if (!successPanel.hidden) return;
      setBusy(button, false, "Send reset link →");
    }
  });

  resetForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    notice.hidden = true;
    const password = document.getElementById("new-password").value;
    const confirmation = document.getElementById("confirm-password").value;
    if (password.length < 12 || password.length > 128) {
      showNotice("Your password must be between 12 and 128 characters.", true);
      return;
    }
    if (password !== confirmation) {
      showNotice("Those passwords don't match. Check both fields and try again.", true);
      return;
    }
    const button = document.getElementById("reset-submit");
    setBusy(button, true, "Update password →");
    try {
      await postJson("/api/v1/auth/reset-password", { token: resetToken, new_password: password });
      window.history.replaceState({}, document.title, window.location.pathname);
      showSuccess("Password updated", "Your password has been changed and existing sessions have been signed out. You can now return to sign in on your devices.");
    } catch (error) {
      showNotice(error.status === 400
        ? "This reset link is invalid, expired or has already been used. Request a new password reset link to continue."
        : "We couldn't update your password just now. Please try again.", true);
    } finally {
      if (!successPanel.hidden) return;
      setBusy(button, false, "Update password →");
    }
  });

  document.getElementById("back-to-login").addEventListener("click", () => {
    window.location.assign("/");
  });
})();
