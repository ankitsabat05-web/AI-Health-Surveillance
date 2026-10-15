(() => {
  const api = window.HealthAPI;
  const auth = window.HealthAuth;
  const charts = window.HealthCharts;

  const today = () => new Date().toISOString().slice(0, 10);
  const daysAgo = (days) => {
    const date = new Date();
    date.setDate(date.getDate() - days);
    return date.toISOString().slice(0, 10);
  };

  async function initOfficialPage() {
    return auth.requireAuth(["health_official"]);
  }

  async function initReports() {
    if (!await initOfficialPage()) return;
    const form = document.getElementById("report-filter");
    const container = document.getElementById("official-reports");
    const load = async () => {
      const params = { limit: 50, offset: 0, report_status: form.elements.report_status.value, region_id: form.elements.region_id.value.trim() };
      try {
        const result = await api.reports(params);
        window.HealthDashboard.renderReportRows(container, result.reports, true);
        document.getElementById("report-count-label").textContent = `${result.total} report${result.total === 1 ? "" : "s"} found`;
      } catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); }
    };
    form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
    await load();
  }

  async function initAnalytics() {
    if (!await initOfficialPage()) return;
    document.getElementById("analytics-date").value = today();
    const load = async () => {
      const date = document.getElementById("analytics-date").value || today();
      try {
        const [overview, daily, summary] = await Promise.all([api.overview(), api.dailySummary(date), api.adminSummary(date)]);
        document.getElementById("analytics-total").textContent = overview.total_reports.toLocaleString();
        document.getElementById("analytics-today").textContent = daily.total_reports.toLocaleString();
        document.getElementById("analytics-diseases").textContent = overview.unique_diseases_reported.toLocaleString();
        document.getElementById("analytics-updated").textContent = `Updated ${new Date(overview.generated_at).toLocaleString()}`;
        charts.renderBars(document.getElementById("status-bars"), [
          { label: "Pending", value: daily.pending_reports },
          { label: "Reviewed", value: daily.reviewed_reports },
          { label: "Rejected", value: daily.rejected_reports },
        ], { color: "#4b78b8" });
        charts.renderBars(document.getElementById("analytics-diseases-bars"), summary.top_reported_diseases || [],
          { label: (item) => item.disease_name, value: (item) => item.report_count });
      } catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); }
    };
    document.getElementById("analytics-filter").addEventListener("submit", (event) => { event.preventDefault(); load(); });
    await load();
  }

  async function initDiseaseMonitor() {
    if (!await initOfficialPage()) return;
    const form = document.getElementById("trend-form");
    form.elements.start_date.value = daysAgo(30);
    form.elements.end_date.value = today();
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const params = Object.fromEntries(new FormData(form));
        const result = await api.diseaseTrend(params);
        document.getElementById("trend-title").textContent = `${result.disease_name} · ${result.start_date} to ${result.end_date}`;
        charts.renderLineChart(document.getElementById("trend-chart"), result.points.map((point) => ({ label: point.report_date, value: point.report_count })));
        document.getElementById("trend-summary").textContent = `${result.points.reduce((sum, point) => sum + point.report_count, 0).toLocaleString()} reports recorded during this period. Counts are reports, not confirmed cases.`;
      } catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); }
    });
    form.requestSubmit();
  }

  async function initHotspots() {
    if (!await initOfficialPage()) return;
    const form = document.getElementById("hotspot-form");
    form.elements.observation_date.value = today();
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      const history = values.get("historical_cases").split(",").map((value) => Number(value.trim()));
      if (history.length < 7 || history.length > 365 || history.some((value) => !Number.isInteger(value) || value < 0)) {
        auth.showMessage(document.getElementById("page-message"), "Enter 7 to 365 historical case counts as comma-separated non-negative whole numbers.");
        return;
      }
      const payload = {
        disease: values.get("disease").trim(),
        region_id: values.get("region_id").trim(),
        region_name: values.get("region_name").trim(),
        observation_date: values.get("observation_date"),
        current_cases: Number(values.get("current_cases")),
        population: Number(values.get("population")),
        historical_cases: history,
      };
      try {
        const result = await api.analyzeHotspot(payload);
        const output = document.getElementById("hotspot-result");
        output.hidden = false;
        document.getElementById("hotspot-level").textContent = result.severity.replaceAll("_", " ");
        document.getElementById("hotspot-explanation").textContent = result.explanation;
        document.getElementById("hotspot-rate").textContent = `${result.current_rate_per_100k.toFixed(1)} / 100k`;
        document.getElementById("hotspot-ratio").textContent = result.rate_ratio === null ? "Not available" : `${result.rate_ratio.toFixed(2)}× baseline`;
        auth.showMessage(document.getElementById("page-message"), "Screening complete. This signal requires official review and does not confirm an outbreak.", "success");
      } catch (error) { auth.showMessage(document.getElementById("page-message"), error.message); }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const page = document.body.dataset.page;
    if (page === "admin-reports") initReports();
    if (page === "admin-analytics") initAnalytics();
    if (page === "admin-disease-monitor") initDiseaseMonitor();
    if (page === "admin-hotspots") initHotspots();
  });
})();