import { loadDashboardState, summarizeSessions } from "../state.js";
import type { AppBootstrap, SessionSummary } from "../types.js";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sectionMarkup(title: string, sessions: SessionSummary[], appPath: string): string {
  const safeTitle = escapeHtml(title);
  const safeAppPath = escapeHtml(appPath);
  if (sessions.length === 0) {
    return `
      <section class="card stack">
        <div class="section-heading"><h2>${safeTitle}</h2><div class="small">No sessions.</div></div>
      </section>
    `;
  }
  return `
    <section class="card stack">
      <div class="section-heading"><h2>${safeTitle}</h2><div class="small">${sessions.length} session(s)</div></div>
      <div class="session-list">
        ${sessions
          .map(
            (session) => `
          <article class="session-card ${session.connected ? "live" : ""} ${session.lastError ? "error" : ""}">
            <div class="session-header">
              <div>
                <div class="session-title">${escapeHtml(session.displayName)}</div>
                <div class="small">${escapeHtml(session.sessionId)} • ${escapeHtml(session.connectorType)}</div>
              </div>
              <span class="status-chip ${session.connected ? "ok" : session.lastError ? "error" : "info"}">${
                session.connected ? "Live" : session.lastError ? "Error" : "Stopped"
              }</span>
            </div>
            <div class="small">Mode: ${escapeHtml(session.inputMode)} • State: ${escapeHtml(session.lifecycleState)}</div>
            <div class="toolbar">
              <a class="btn" href="${safeAppPath}/operator/${encodeURIComponent(session.sessionId)}">Operator</a>
              <a class="btn" href="${safeAppPath}/session/${encodeURIComponent(session.sessionId)}">User view</a>
              <a class="btn" href="${safeAppPath}/replay/${encodeURIComponent(session.sessionId)}">Replay</a>
            </div>
          </article>
        `,
          )
          .join("")}
      </div>
    </section>
  `;
}

export async function renderDashboard(root: HTMLElement, bootstrap: AppBootstrap): Promise<void> {
  const safeTitle = escapeHtml(bootstrap.title);
  const safeAppPath = escapeHtml(bootstrap.app_path);
  root.innerHTML = `
    <div class="page">
      <section class="card stack">
        <div class="small">Reference implementation</div>
        <h1>${safeTitle}</h1>
        <div class="toolbar">
          <a class="btn" href="${safeAppPath}/connect">Quick Connect</a>
          <button id="dashboard-refresh" class="btn">Refresh</button>
        </div>
        <div id="dashboard-status" class="status-chip info">Loading sessions…</div>
      </section>
      <div id="dashboard-content" class="page"></div>
    </div>
  `;
  const status = root.querySelector<HTMLElement>("#dashboard-status");
  const content = root.querySelector<HTMLElement>("#dashboard-content");
  if (!status || !content) throw new Error("dashboard shell is incomplete");
  async function loadSessions(statusEl: HTMLElement, contentEl: HTMLElement): Promise<void> {
    try {
      const sessions = await loadDashboardState();
      const groups = summarizeSessions(sessions);
      statusEl.className = "status-chip ok";
      statusEl.textContent = `${sessions.length} session(s) loaded`;
      contentEl.innerHTML = [
        sectionMarkup("Running", groups.running, bootstrap.app_path),
        sectionMarkup("Stopped", groups.stopped, bootstrap.app_path),
        sectionMarkup("Degraded", groups.degraded, bootstrap.app_path),
      ].join("");
    } catch (error) {
      statusEl.className = "status-chip error";
      statusEl.textContent = `Dashboard failed to load: ${String(error)}`;
      contentEl.innerHTML = `<section class="card"><div class="small">Unable to load session state.</div></section>`;
    }
  }
  root.querySelector<HTMLButtonElement>("#dashboard-refresh")?.addEventListener("click", () => {
    void loadSessions(status, content);
  });
  await loadSessions(status, content);
}
