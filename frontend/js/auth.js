(() => {
  const api = window.HealthAPI;

  function redirectFor(profile) {
    if (profile.role === "health_official") return "admin/dashboard.html";
    if (profile.role === "user") return "user/dashboard.html";
    return null;
  }

  function showMessage(target, message, type = "error") {
    if (!target) return;
    target.textContent = message;
    target.className = `notice notice--${type}`;
    target.hidden = false;
  }

  async function requireAuth(roles = []) {
    const token = localStorage.getItem(api.tokenKey);
    if (!token) {
      location.replace("../index.html");
      return null;
    }
    try {
      const profile = await api.profile();
      localStorage.setItem(api.profileKey, JSON.stringify(profile));
      if (roles.length && !roles.includes(profile.role)) {
        const destination = redirectFor(profile);
        if (destination) location.replace(`../${destination}`);
        else showPageError("This account role does not have a matching frontend portal. Contact your system administrator.");
        return null;
      }
      document.querySelectorAll("[data-profile-name]").forEach((node) => { node.textContent = profile.full_name; });
      document.querySelectorAll("[data-profile-role]").forEach((node) => { node.textContent = profile.role.replaceAll("_", " "); });
      return profile;
    } catch (error) {
      if (!localStorage.getItem(api.tokenKey)) {
        location.replace("../index.html");
      } else {
        showPageError(error.message);
      }
      return null;
    }
  }

  function showPageError(message) {
    let target = document.querySelector("[data-page-message], #dashboard-error, #page-message");
    if (!target) {
      target = document.createElement("div");
      target.className = "notice";
      const content = document.querySelector(".page-content");
      if (content) content.prepend(target);
    }
    showMessage(target, message);
  }

  function logout() {
    localStorage.removeItem(api.tokenKey);
    localStorage.removeItem(api.profileKey);
    location.replace("../index.html");
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-logout]")) logout();
  });

  document.addEventListener("DOMContentLoaded", () => {
    const setupMessage = document.querySelector("[data-setup-message]");
    if (location.protocol === "file:" && setupMessage) {
      showMessage(
        setupMessage,
        "This page is opened directly from a file. For login to work, serve the frontend at http://127.0.0.1:5500 and run the API at http://127.0.0.1:8000.",
        "info",
      );
    }

    document.querySelectorAll("[data-auth-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        const message = form.querySelector("[data-form-message]");
        if (button) button.disabled = true;
        if (message) message.hidden = true;
        try {
          const fields = new FormData(form);
          let profile;
          if (form.dataset.authForm === "register") {
            profile = await api.register({
              full_name: fields.get("full_name").trim(),
              email: fields.get("email").trim(),
              password: fields.get("password"),
            });
            showMessage(message, "Account created. Sign in with your new account.", "success");
            form.reset();
            return;
          }
          const result = await api.login(fields.get("email").trim(), fields.get("password"));
          localStorage.setItem(api.tokenKey, result.access_token);
          profile = await api.profile();
          localStorage.setItem(api.profileKey, JSON.stringify(profile));
          const destination = redirectFor(profile);
          if (destination) location.replace(destination);
          else showMessage(message, "This account role does not have a matching frontend portal. Contact your system administrator.");
        } catch (error) {
          showMessage(message, error.message);
        } finally {
          if (button) button.disabled = false;
        }
      });
    });

    const switcher = document.querySelector("[data-auth-switch]");
    if (switcher) {
      switcher.addEventListener("click", () => {
        const login = document.querySelector("#login-panel");
        const register = document.querySelector("#register-panel");
        const showRegister = register.hidden;
        login.hidden = showRegister;
        register.hidden = !showRegister;
        switcher.textContent = showRegister ? "Already have an account? Sign in" : "Create a personal account";
      });
    }
  });

  window.HealthAuth = { requireAuth, logout, showMessage };
})();