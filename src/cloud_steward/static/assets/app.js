const state = { currentPlan: null };
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value = "") {
  return value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

async function loadStatus() {
  const status = await api("/api/status");
  $("#integration-count").textContent = status.integrations.length;
  $("#arch").textContent = status.architecture;
  $("#system-state").textContent = status.integrations.some((item) => !item.configured) ? "demo-ready" : "live";
  $("#integrations").innerHTML = status.integrations.map((item) => `
    <div class="integration">
      <i class="${item.configured ? "" : "sample"}"></i>
      <span><b>${escapeHtml(item.name)}</b><small>${escapeHtml(item.detail)}</small></span>
      <code>${escapeHtml(item.mode)}</code>
    </div>`).join("");
  $("#safeguards").innerHTML = status.safeguards.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderPlan(plan) {
  state.currentPlan = plan;
  $("#result-section").hidden = false;
  $("#result-title").textContent = plan.summary;
  $("#risk-chip").textContent = `${plan.overall_risk} risk · ${plan.status}`;
  $("#context-banner").innerHTML = `<b>Context findings</b><br>${(plan.context_findings.length ? plan.context_findings : ["No governed resources matched the query."]).map(escapeHtml).join(" · ")}`;
  $("#plan-actions").innerHTML = plan.actions.map((action) => `
    <article class="action-item">
      <span class="action-number">${String(action.order).padStart(2, "0")}</span>
      <div class="action-copy">
        <h3>${escapeHtml(action.action)}</h3>
        <p>${escapeHtml(action.reason)}</p>
        <div class="action-meta">
          <div><b>Target</b><span>${escapeHtml(action.target)}</span></div>
          <div><b>Risk</b><span>${escapeHtml(action.risk)}${action.mutation ? " · mutation" : " · read-only"}</span></div>
          <div><b>Verify</b><span>${escapeHtml(action.verification)}</span></div>
          <div><b>Rollback</b><span>${escapeHtml(action.rollback)}</span></div>
        </div>
      </div>
    </article>`).join("");
  $("#approval-status").textContent = "No approval recorded";
  $("#approve-button").disabled = false;
  $("#result-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadHistory() {
  const plans = await api("/api/plans");
  $("#plan-count").textContent = plans.length;
  $("#history").innerHTML = plans.length ? plans.map((record) => `
    <article class="history-item">
      <code>${escapeHtml(record.id.slice(0, 8))}</code>
      <div><h3>${escapeHtml(record.goal)}</h3><p>${new Date(record.created_at).toLocaleString()} · ${escapeHtml(record.context.provider)}</p></div>
      <span>${escapeHtml(record.status)}</span>
    </article>`).join("") : '<p class="empty">No plans yet. Draft the first governed action.</p>';
}

$("#plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const error = $("#form-error");
  error.textContent = "";
  button.disabled = true;
  button.querySelector(".button-label").textContent = "Collecting governed context…";
  try {
    const plan = await api("/api/plans", {
      method: "POST",
      body: JSON.stringify({
        goal: $("#goal").value,
        context_query: $("#context-query").value,
        environment: $("#environment").value,
        dry_run: true,
      }),
    });
    renderPlan(plan);
    await Promise.all([loadHistory(), loadStatus()]);
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    button.disabled = false;
    button.querySelector(".button-label").textContent = "Generate governed plan";
  }
});

$("#approve-button").addEventListener("click", async () => {
  if (!state.currentPlan) return;
  const button = $("#approve-button");
  button.disabled = true;
  try {
    const record = await api(`/api/plans/${state.currentPlan.id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by: "demo-reviewer", note: "Demo approval only; no execution requested." }),
    });
    $("#approval-status").textContent = `Recorded for ${record.approved_by}; execution remains disabled.`;
    $("#risk-chip").textContent = `${state.currentPlan.overall_risk} risk · approved`;
    await loadHistory();
  } catch (requestError) {
    $("#approval-status").textContent = requestError.message;
    button.disabled = false;
  }
});

$("#refresh-history").addEventListener("click", loadHistory);
document.querySelectorAll("[data-scroll-to]").forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.scrollTo}`).scrollIntoView({ behavior: "smooth" })));
$("[data-demo]").addEventListener("click", () => {
  $("#goal").value = "Diagnose elevated checkout latency, protect invoice generation, and prepare a reversible capacity change for approval.";
  $("#context-query").value = "checkout billing invoice production critical";
  $("#composer").scrollIntoView({ behavior: "smooth" });
});

Promise.all([loadStatus(), loadHistory()]).catch((error) => {
  $("#system-state").textContent = "degraded";
  $("#form-error").textContent = error.message;
});
