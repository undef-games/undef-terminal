import { loadDashboardState, summarizeSessions } from "../state.js";
function sectionMarkup(title, sessions, appPath) {
    if (sessions.length === 0) {
        return `
      <section class="card stack">
        <div class="section-heading"><h2>${title}</h2><div class="small">No sessions.</div></div>
      </section>
    `;
    }
    return `
    <section class="card stack">
      <div class="section-heading"><h2>${title}</h2><div class="small">${sessions.length} session(s)</div></div>
      <div class="session-list">
        ${sessions
        .map((session) => `
          <article class="session-card ${session.connected ? "live" : ""} ${session.lastError ? "error" : ""}">
            <div class="session-header">
              <div>
                <div class="session-title">${session.displayName}</div>
                <div class="small">${session.sessionId} • ${session.connectorType}</div>
              </div>
              <span class="status-chip ${session.connected ? "ok" : session.lastError ? "error" : "info"}">${session.connected ? "Live" : session.lastError ? "Error" : "Stopped"}</span>
            </div>
            <div class="small">Mode: ${session.inputMode} • State: ${session.lifecycleState}</div>
            <div class="toolbar">
              <a class="btn" href="${appPath}/operator/${encodeURIComponent(session.sessionId)}">Operator</a>
              <a class="btn" href="${appPath}/session/${encodeURIComponent(session.sessionId)}">User view</a>
              <a class="btn" href="${appPath}/replay/${encodeURIComponent(session.sessionId)}">Replay</a>
            </div>
          </article>
        `)
        .join("")}
      </div>
    </section>
  `;
}
export async function renderDashboard(root, bootstrap) {
    root.innerHTML = `
    <div class="page">
      <section class="card stack">
        <div class="small">Reference implementation</div>
        <h1>${bootstrap.title}</h1>
        <div id="dashboard-status" class="status-chip info">Loading sessions…</div>
      </section>
      <div id="dashboard-content" class="page"></div>
    </div>
  `;
    const status = root.querySelector("#dashboard-status");
    const content = root.querySelector("#dashboard-content");
    if (!status || !content)
        throw new Error("dashboard shell is incomplete");
    try {
        const sessions = await loadDashboardState();
        const groups = summarizeSessions(sessions);
        status.className = "status-chip ok";
        status.textContent = `${sessions.length} session(s) loaded`;
        content.innerHTML = [
            sectionMarkup("Running", groups.running, bootstrap.app_path),
            sectionMarkup("Stopped", groups.stopped, bootstrap.app_path),
            sectionMarkup("Degraded", groups.degraded, bootstrap.app_path),
        ].join("");
    }
    catch (error) {
        status.className = "status-chip error";
        status.textContent = `Dashboard failed to load: ${String(error)}`;
        content.innerHTML = `<section class="card"><div class="small">Unable to load session state.</div></section>`;
    }
}
