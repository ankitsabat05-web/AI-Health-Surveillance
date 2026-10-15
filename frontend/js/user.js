(() => {
  const api = window.HealthAPI;
  const auth = window.HealthAuth;

  async function initReportForm() {
    if (!await auth.requireAuth(["user"])) return;
    const form = document.getElementById("health-report-form");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      const payload = {
        disease_name: values.get("disease_name").trim(),
        symptoms: values.get("symptoms").split(",").map((value) => value.trim()).filter(Boolean),
        region_id: values.get("region_id").trim(),
        description: values.get("description").trim() || null,
      };
      const button = form.querySelector('[type="submit"]');
      button.disabled = true;
      try {
        const result = await api.createReport(payload);
        auth.showMessage(document.getElementById("form-message"), `Report #${result.id} submitted. Status: ${result.status.replaceAll("_", " ")}. This is a report, not a confirmed diagnosis.`, "success");
        form.reset();
      } catch (error) { auth.showMessage(document.getElementById("form-message"), error.message); }
      finally { button.disabled = false; }
    });

    const screening = document.getElementById("symptom-screen-form");
    screening.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(screening);
      try {
        const result = await api.analyzeSymptoms({
          symptoms: values.get("symptoms").split(",").map((value) => value.trim()).filter(Boolean),
          age: values.get("age") ? Number(values.get("age")) : null,
          duration_days: values.get("duration_days") ? Number(values.get("duration_days")) : null,
        });
        const output = document.getElementById("screening-result");
        output.hidden = false;
        document.getElementById("screening-urgency").textContent = result.urgency.replaceAll("_", " ");
        document.getElementById("screening-guidance").replaceChildren(...result.guidance.map((item) => {
          const li = document.createElement("li"); li.textContent = item; return li;
        }));
        document.getElementById("screening-disclaimer").textContent = "Preliminary screening only; this is not a diagnosis. Seek urgent care for severe or worsening symptoms.";
      } catch (error) { auth.showMessage(document.getElementById("screening-message"), error.message); }
    });
  }

  async function initHistory() {
    if (!await auth.requireAuth(["user"])) return;
    try {
      const result = await api.myReports({ limit: 100, offset: 0 });
      const body = document.getElementById("report-history");
      if (!result.reports.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty-cell">You have not submitted a report yet.</td></tr>';
        return;
      }
      result.reports.forEach((report) => {
        const row = document.createElement("tr");
        [new Date(report.created_at).toLocaleString(), report.disease_name || "Unspecified", report.region_id, report.symptoms.join(", ")].forEach((text) => {
          const cell = document.createElement("td"); cell.textContent = text; row.append(cell);
        });
        const cell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `status status--${report.status}`;
        badge.textContent = report.status.replaceAll("_", " ");
        cell.append(badge); row.append(cell); body.append(row);
      });
    } catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); }
  }

  async function initProfile() {
    const profile = await auth.requireAuth(["user"]);
    if (!profile) return;
    const form = document.getElementById("profile-form");
    form.elements.full_name.value = profile.full_name;
    document.getElementById("profile-email").textContent = profile.email;
    document.getElementById("profile-role").textContent = profile.role.replaceAll("_", " ");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const updated = await api.updateProfile({ full_name: form.elements.full_name.value.trim() });
        localStorage.setItem(api.profileKey, JSON.stringify(updated));
        auth.showMessage(document.getElementById("profile-message"), "Your profile has been updated.", "success");
      } catch (error) { auth.showMessage(document.getElementById("profile-message"), error.message); }
    });
    document.getElementById("password-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const passwordForm = event.currentTarget;
      try {
        await api.changePassword({
          current_password: passwordForm.elements.current_password.value,
          new_password: passwordForm.elements.new_password.value,
        });
        passwordForm.reset();
        auth.showMessage(document.getElementById("password-message"), "Password changed successfully.", "success");
      } catch (error) { auth.showMessage(document.getElementById("password-message"), error.message); }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    if (page === "report-health") initReportForm();
    if (page === "report-history") initHistory();
    if (page === "user-profile") initProfile();
  });
})();