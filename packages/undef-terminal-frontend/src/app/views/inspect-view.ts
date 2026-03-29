//
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
// SPDX-License-Identifier: AGPL-3.0-or-later
//

import type { AppBootstrap } from "../types.js";
import { renderAppHeader } from "./app-header.js";

export async function renderInspect(root: HTMLElement, bootstrap: AppBootstrap): Promise<void> {
  if (!bootstrap.session_id) throw new Error("inspect bootstrap missing session_id");

  root.innerHTML = `
    <div class="page inspect-page">
      ${renderAppHeader(bootstrap, "inspect")}
      <div class="inspect-layout">
        <div class="inspect-toolbar">
          <select id="inspect-method-filter">
            <option value="">All Methods</option>
            <option>GET</option><option>POST</option><option>PUT</option>
            <option>DELETE</option><option>PATCH</option>
          </select>
          <input id="inspect-url-filter" type="text" placeholder="Filter URL..." />
          <span id="inspect-count">0 requests</span>
        </div>
        <div class="inspect-split">
          <div id="inspect-list" class="inspect-list"></div>
          <div id="inspect-detail" class="inspect-detail">
            <div class="inspect-empty">Select a request to view details</div>
          </div>
        </div>
      </div>
    </div>
  `;
}
