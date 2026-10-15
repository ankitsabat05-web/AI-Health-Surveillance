(() => {
  function renderBars(container, items, { label = (item) => item.label, value = (item) => item.value, color = "#168b83" } = {}) {
    if (!container) return;
    if (!items?.length) {
      container.innerHTML = '<p class="empty-state">No report data is available for this period.</p>';
      return;
    }
    const max = Math.max(1, ...items.map(value));
    container.innerHTML = items.map((item) => {
      const amount = Number(value(item)) || 0;
      const width = Math.max(amount > 0 ? 4 : 0, (amount / max) * 100);
      const row = document.createElement("div");
      row.className = "bar-row";
      const name = document.createElement("span");
      name.className = "bar-row__label";
      name.textContent = label(item);
      const track = document.createElement("span");
      track.className = "bar-row__track";
      const bar = document.createElement("span");
      bar.className = "bar-row__fill";
      bar.style.width = `${width}%`;
      bar.style.backgroundColor = color;
      track.append(bar);
      const count = document.createElement("strong");
      count.className = "bar-row__value";
      count.textContent = amount.toLocaleString();
      row.append(name, track, count);
      return row;
    }).forEach((row) => container.append(row));
  }

  function renderLineChart(container, points) {
    if (!container) return;
    const clean = (points || []).filter((point) => Number.isFinite(Number(point.value)));
    if (clean.length < 2) {
      container.innerHTML = '<p class="empty-state">Not enough points to draw a trend yet.</p>';
      return;
    }
    const width = 720, height = 230, pad = 28;
    const max = Math.max(1, ...clean.map((point) => Number(point.value)));
    const coords = clean.map((point, index) => ({
      x: pad + index * (width - pad * 2) / (clean.length - 1),
      y: height - pad - (Number(point.value) / max) * (height - pad * 2),
      ...point,
    }));
    const path = coords.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Daily health report trend chart");
    const line = document.createElementNS(svg.namespaceURI, "path");
    line.setAttribute("d", path);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "#168b83");
    line.setAttribute("stroke-width", "3");
    line.setAttribute("stroke-linecap", "round");
    line.setAttribute("stroke-linejoin", "round");
    svg.append(line);
    coords.forEach((point) => {
      const dot = document.createElementNS(svg.namespaceURI, "circle");
      dot.setAttribute("cx", point.x);
      dot.setAttribute("cy", point.y);
      dot.setAttribute("r", "4");
      dot.setAttribute("fill", "#168b83");
      svg.append(dot);
    });
    const axis = document.createElementNS(svg.namespaceURI, "path");
    axis.setAttribute("d", `M ${pad} ${height - pad} H ${width - pad}`);
    axis.setAttribute("stroke", "#dce5e4");
    svg.append(axis);
    container.replaceChildren(svg);
  }

  window.HealthCharts = { renderBars, renderLineChart };
})();