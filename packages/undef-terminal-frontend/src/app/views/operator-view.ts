//
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
// SPDX-License-Identifier: AGPL-3.0-or-later
//

import { clearRuntime, loadOperatorWorkspaceState, requestAnalysis, switchSessionMode } from "../state.js";
import type { AppBootstrap, SessionSummary } from "../types.js";
import { mountHijackWidget } from "../widgets/hijack-widget-host.js";
import { renderAppHeader } from "./app-header.js";

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function infoRow(label: string, value: unknown): string {
  return `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
    <span class="small">${esc(label)}</span>
    <span style="font-weight:600">${esc(String(value ?? "\u2014"))}</span>
  </div>`;
}

function renderTags(tags: string[]): string {
  if (!tags.length) return '<span class="small">none</span>';
  return `<div class="tag-list">${tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>`;
}

function sidebarHtml(s: SessionSummary | null, appPath: string, sessionId: string): string {
  const name = s?.displayName ?? sessionId;
  const isOpen = s?.inputMode === "open";
  const liveBadge = s?.connected
    ? '<span class="badge" style="background:rgba(49,196,141,0.15);border:1px solid rgba(49,196,141,0.4);color:#b7f7dd">Live</span>'
    : '<span class="badge badge-visibility">Offline</span>';

  return `<section class="card stack">
    <div class="small" style="text-transform:uppercase;letter-spacing:0.06em">Operator Console</div>
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span class="session-title">${esc(name)}</span>${liveBadge}
    </div>
    <div id="operator-status" class="status-chip info">Loading\u2026</div>

    <div class="small" style="text-transform:uppercase;letter-spacing:0.06em;margin-top:4px">Input Mode</div>
    <div class="toolbar" style="margin:0">
      <button class="btn${isOpen ? " primary" : ""}" id="btn-open">Shared</button>
      <button class="btn${!isOpen ? " primary" : ""}" id="btn-hijack">Exclusive</button>
    </div>

    <div class="small" style="text-transform:uppercase;letter-spacing:0.06em">Actions</div>
    <div class="toolbar" style="margin:0">
      <a class="btn" href="${esc(appPath)}/replay/${encodeURIComponent(sessionId)}">View replay</a>
      <button class="btn" id="btn-clear">Clear runtime</button>
    </div>

    <details style="margin-top:2px">
      <summary class="small" style="cursor:pointer;user-select:none">Advanced</summary>
      <div class="toolbar" style="margin:6px 0 0">
        <button class="btn" id="btn-analyze">Analyze screen</button>
      </div>
      <div class="small" style="margin-top:4px;color:var(--muted)">AI-readable description of current terminal contents.</div>
    </details>

    <div class="small" style="text-transform:uppercase;letter-spacing:0.06em">Session Info</div>
    <div>
      ${infoRow("Connector", s?.connectorType)}
      ${infoRow("State", s?.lifecycleState)}
      ${infoRow("Owner", s?.owner)}
      ${infoRow("Visibility", s?.visibility)}
      ${infoRow("Auto-start", s?.autoStart ? "yes" : "no")}
    </div>

    <div class="small" style="text-transform:uppercase;letter-spacing:0.06em">Tags</div>
    ${renderTags(s?.tags ?? [])}

    <button class="btn" id="btn-restart" style="margin-top:auto">Restart session</button>
  </section>`;
}

export async function renderOperator(root: HTMLElement, bootstrap: AppBootstrap): Promise<void> {
  if (!bootstrap.session_id) throw new Error("operator bootstrap missing session_id");
  const sessionId = bootstrap.session_id;
  const appPath = esc(bootstrap.app_path);

  root.innerHTML = `
    <div class="page">
      ${renderAppHeader(bootstrap, "operator")}
      <div class="layout">
        ${sidebarHtml(null, appPath, sessionId)}
        <section class="card"><div id="widget"></div></section>
      </div>
    </div>`;

  const widget = root.querySelector<HTMLElement>("#widget");
  if (!widget) throw new Error("operator shell is incomplete");

  // Wire all sidebar buttons — called after each sidebar re-render.
  const wire = (): void => {
    root.querySelector<HTMLButtonElement>("#btn-open")?.addEventListener("click", () => {
      void switchSessionMode(sessionId, "open").then(() => void refresh());
    });
    root.querySelector<HTMLButtonElement>("#btn-hijack")?.addEventListener("click", () => {
      void switchSessionMode(sessionId, "hijack").then(() => void refresh());
    });
    root.querySelector<HTMLButtonElement>("#btn-clear")?.addEventListener("click", () => {
      void clearRuntime(sessionId)
        .then(() => void refresh())
        .catch((e) => setStatus("error", `Clear failed: ${String(e)}`));
    });
    root.querySelector<HTMLButtonElement>("#btn-analyze")?.addEventListener("click", () => {
      void requestAnalysis(sessionId)
        .then((a) => window.alert(a))
        .catch((e) => setStatus("error", `Analyze failed: ${String(e)}`));
    });
    root.querySelector<HTMLButtonElement>("#btn-restart")?.addEventListener("click", () => void refresh());
  };

  const setStatus = (tone: string, text: string): void => {
    const el = root.querySelector<HTMLElement>("#operator-status");
    if (el) {
      el.className = `status-chip ${tone}`;
      el.textContent = text;
    }
  };

  const refresh = async (): Promise<void> => {
    const state = await loadOperatorWorkspaceState(sessionId);
    setStatus(state.status.tone, state.status.text);
    // Re-render sidebar with fresh data
    const sidebar = root.querySelector(".layout > section:first-child");
    if (sidebar) {
      const tmp = document.createElement("div");
      tmp.innerHTML = sidebarHtml(state.session.summary, appPath, sessionId);
      const next = tmp.querySelector("section");
      if (next) {
        sidebar.replaceWith(next);
        // Restore status text after re-render
        setStatus(state.status.tone, state.status.text);
        wire();
      }
    }
  };

  try {
    await refresh();
    const widgetState = mountHijackWidget(widget, sessionId, "operator");
    if (!widgetState.mounted) {
      setStatus("error", widgetState.error ?? "Widget mount failed");
    }
  } catch (error) {
    setStatus("error", `Operator workspace failed to load: ${String(error)}`);
  }
  wire();
}
