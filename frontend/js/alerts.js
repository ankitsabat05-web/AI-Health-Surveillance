(() => {
  const api = window.HealthAPI;
  const auth = window.HealthAuth;
  const labels = {
    critical: "Critical", high: "High", moderate: "Moderate", low: "Low",
  };

  async function init() {
    if (!await auth.requireAuth(["health_official"])) return;
    const form = document.getElementById("alert-filter");
    const list = document.getElementById("alert-list");
    const load = async () => {
      try {
        const values = Object.fromEntries(new FormData(form));
        const result = await api.alerts({ ...values, limit: 50, offset: 0 });
        document.getElementById("alert-count").textContent = `${result.total} alert${result.total === 1 ? "" : "s"}`;
        list.replaceChildren();
        if (!result.items.length) {
          list.innerHTML = '<div class="empty-state">No alerts match these filters.</div>';
          return;
        }
        result.items.forEach((alert) => {
          const card = document.createElement("article");
          card.className = "alert-card";
          const heading = document.createElement("div");
          heading.className = "alert-card__heading";
          const title = document.createElement("h3");
          title.textContent = alert.title;
          const severity = document.createElement("span");
          severity.className = `severity severity--${alert.severity}`;
          severity.textContent = labels[alert.severity] || alert.severity;
          heading.append(title, severity);
          const description = document.createElement("p");
          description.textContent = alert.description;
          const meta = document.createElement("p");
          meta.className = "muted";
          meta.textContent = `${alert.disease_name || "Unspecified disease"} · ${alert.region_id || "Region not specified"} · ${new Date(alert.created_at).toLocaleString()}`;
          const status = document.createElement("span");
          status.className = `status status--${alert.status}`;
          status.textContent = alert.status;
          card.append(heading, description, meta, status);
          const actions = document.createElement("div");
          actions.className = "inline-actions";
          if (alert.status === "new") actions.append(actionButton("Acknowledge", "acknowledge", alert.id, load));
          if (alert.status !== "resolved") actions.append(actionButton("Resolve", "resolve", alert.id, load));
          if (actions.childElementCount) card.append(actions);
          list.append(card);
        });
      } catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); }
    };
    form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
    await load();
  }

  function actionButton(label, action, id, reload) {
    const button = document.createElement("button");
    button.className = action === "resolve" ? "button button--quiet" : "button button--small";
    button.textContent = label;
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { await api.alertAction(id, action); await reload(); }
      catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); button.disabled = false; }
    });
    return button;
  }

  document.addEventListener("DOMContentLoaded", init);
})();