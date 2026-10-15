(() => {
  function renderRegions(container, regions = []) {
    if (!container) return;
    if (!regions.length) {
      container.innerHTML = '<p class="empty-state">Regional submissions will appear here when reports are received.</p>';
      return;
    }
    window.HealthCharts.renderBars(container, regions, {
      label: (item) => item.region_id,
      value: (item) => item.report_count,
      color: "#4b78b8",
    });
  }
  window.HealthMap = { renderRegions };
})();