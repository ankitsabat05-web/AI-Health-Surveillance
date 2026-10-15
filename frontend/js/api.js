(() => {
  const API_BASE = (window.HEALTH_API_BASE || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
  const TOKEN_KEY = "health-surveillance-token";
  const PROFILE_KEY = "health-surveillance-profile";

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal });
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error("The health service did not respond within 15 seconds. Make sure the backend is running, then try again.");
      }
      throw new Error("Could not connect to the health service. Make sure the backend is running at the configured API address and open this frontend from an allowed http://localhost or http://127.0.0.1 origin.");
    } finally {
      clearTimeout(timeout);
    }

    if (response.status === 204) return null;
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(PROFILE_KEY);
      }
      let message = data?.error?.message || data?.detail || `Request failed (${response.status}).`;
      if (data?.error?.details?.length) {
        message += ` ${data.error.details.map((item) => `${item.field}: ${item.message}`).join("; ")}`;
      }
      throw new Error(Array.isArray(message) ? message.map((item) => item.msg || item.message).join(", ") : message);
    }
    return data;
  }

  const query = (values) => {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, value);
    });
    const value = params.toString();
    return value ? `?${value}` : "";
  };

  window.HealthAPI = {
    base: API_BASE,
    request,
    query,
    tokenKey: TOKEN_KEY,
    profileKey: PROFILE_KEY,
    login: (email, password) => {
      const form = new URLSearchParams({ username: email, password });
      return request("/auth/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: form });
    },
    register: (payload) => request("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
    profile: () => request("/users/me"),
    myReports: (params = {}) => request(`/reports/my-reports${query(params)}`),
    reports: (params = {}) => request(`/reports/${query(params)}`),
    createReport: (payload) => request("/reports/", { method: "POST", body: JSON.stringify(payload) }),
    updateReportStatus: (id, status) => request(`/reports/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
    overview: () => request("/dashboard/overview"),
    adminSummary: (date) => request(`/admin/dashboard${query({ report_date: date })}`),
    dailySummary: (date) => request(`/admin/reports/daily${query({ report_date: date })}`),
    diseaseTrend: (params) => request(`/admin/trends/disease${query(params)}`),
    alerts: (params = {}) => request(`/alerts${query(params)}`),
    alertAction: (id, action) => request(`/alerts/${id}/${action}`, { method: "POST" }),
    analyzeSymptoms: (payload) => request("/ai/symptoms/analyze", { method: "POST", body: JSON.stringify(payload) }),
    analyzeHotspot: (payload) => request("/ai/hotspots/analyze", { method: "POST", body: JSON.stringify(payload) }),
    aiHealth: () => request("/ai/health"),
    updateProfile: (payload) => request("/users/me", { method: "PATCH", body: JSON.stringify(payload) }),
    changePassword: (payload) => request("/users/me/change-password", { method: "POST", body: JSON.stringify(payload) }),
  };
})();