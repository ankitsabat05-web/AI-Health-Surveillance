(() => {
  const api = window.HealthAPI;
  const auth = window.HealthAuth;
  const charts = window.HealthCharts;

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = Number(value || 0).toLocaleString();
  }
  function reportStatus(status) {
    return `<span class="status status--${status}">${status.replaceAll("_", " ")}</span>`;
  }
  function renderReportRows(container, reports, official = false) {
    if (!container) return;
    if (!reports.length) {
      container.innerHTML = '<tr><td colspan="5" class="empty-cell">No reports yet.</td></tr>';
      return;
    }
    container.replaceChildren();
    reports.forEach((report) => {
      const row = document.createElement("tr");
      const fields = [
        `#${report.id}`,
        report.disease_name || "Unspecified",
        report.region_id || "—",
        new Date(report.created_at).toLocaleDateString(),
      ];
      fields.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      const statusCell = document.createElement("td");
      statusCell.innerHTML = reportStatus(report.status);
      if (official) {
        const select = document.createElement("select");
        select.setAttribute("aria-label", `Update status for report ${report.id}`);
        ["submitted", "under_review", "verified", "rejected"].forEach((status) => {
          const option = document.createElement("option");
          option.value = status;
          option.textContent = status.replaceAll("_", " ");
          option.selected = status === report.status;
          select.append(option);
        });
        select.addEventListener("change", async () => {
          select.disabled = true;
          try {
            await api.updateReportStatus(report.id, select.value);
            await loadOfficialReports();
          } catch (error) {
            auth.showMessage(document.querySelector("[data-page-message]"), error.message);
            select.value = report.status;
          } finally {
            select.disabled = false;
          }
        });
        statusCell.append(select);
      } else {
        statusCell.innerHTML = reportStatus(report.status);
      }
      row.append(statusCell);
      container.append(row);
    });
  }

  async function loadOfficialReports() {
    const result = await api.reports({ limit: 8, offset: 0 });
    renderReportRows(document.getElementById("recent-reports"), result.reports, true);
    setText("report-total", result.total);
    charts.renderBars(document.getElementById("disease-bars"),
      (await api.adminSummary()).top_reported_diseases || [],
      { label: (item) => item.disease_name, value: (item) => item.report_count });
  }

  async function loadAdminDashboard() {
    const profile = await auth.requireAuth(["health_official"]);
    if (!profile) return;
    const results = await Promise.allSettled([api.overview(), api.adminSummary()]);
    if (results[0].status === "fulfilled") {
      const data = results[0].value;
      setText("report-total", data.total_reports);
      setText("reports-today", data.reports_today);
      setText("reports-week", data.reports_last_7_days);
      setText("disease-count", data.unique_diseases_reported);
    }
    if (results[1].status === "fulfilled") {
      const data = results[1].value;
      charts.renderBars(document.getElementById("disease-bars"), data.top_reported_diseases, {
        label: (item) => item.disease_name, value: (item) => item.report_count,
      });
      window.HealthMap?.renderRegions(document.getElementById("region-bars"), data.regions_with_most_reports);
    }
    try {
      await loadOfficialReports();
      document.getElementById("dashboard-error")?.setAttribute("hidden", "");
    } catch (error) {
      auth.showMessage(document.getElementById("dashboard-error"), error.message);
    }
    const failures = results.filter((result) => result.status === "rejected");
    if (failures.length) auth.showMessage(document.getElementById("dashboard-error"), failures[0].reason.message);
  }

  async function loadUserDashboard() {
    const profile = await auth.requireAuth(["user"]);
    if (!profile) return;
    try {
      const result = await api.myReports({ limit: 100, offset: 0 });
      const reports = result.reports || [];
      setText("my-report-count", result.total);
      setText("my-pending-count", reports.filter((report) => ["submitted", "under_review"].includes(report.status)).length);
      const latest = document.getElementById("latest-report");
      if (latest) renderReportRows(latest, reports.slice(0, 5));
      document.getElementById("dashboard-error")?.setAttribute("hidden", "");
    } catch (error) {
      auth.showMessage(document.getElementById("dashboard-error"), error.message);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.page === "admin-dashboard") loadAdminDashboard();
    if (document.body.dataset.page === "user-dashboard") loadUserDashboard();
  });
  window.HealthDashboard = { renderReportRows, loadOfficialReports };
})();