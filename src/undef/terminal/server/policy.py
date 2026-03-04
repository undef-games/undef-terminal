#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Session-scoped policy decisions for the hosted server app."""

from __future__ import annotations

from dataclasses import dataclass

from undef.terminal.server.auth import Principal
from undef.terminal.server.models import AuthConfig, SessionDefinition


@dataclass(slots=True)
class SessionPolicyResolver:
    """Map principals to browser roles for a given session definition."""

    auth: AuthConfig

    def role_for(self, principal: Principal, session: SessionDefinition) -> str:
        requested = principal.requested_role
        if requested in {"viewer", "operator", "admin"}:
            return requested
        if self.auth.mode not in {"none", "dev"} and principal.name == "anonymous":
            return "viewer"
        if principal.surface == "operator":
            return "admin"
        if principal.surface == "user":
            return "operator" if session.input_mode == "open" else "viewer"
        if self.auth.mode in {"none", "dev"}:
            return "admin"
        if session.visibility == "operator":
            return "viewer"
        return "viewer"
