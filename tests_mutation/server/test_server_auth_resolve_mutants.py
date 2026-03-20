#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Mutation-killing tests for server/auth.py — principal resolution functions."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

from undef.terminal.server.models import AuthConfig

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TEST_KEY = "uterm-test-secret-32-byte-minimum-key"


def _jwt_auth_config(key: str = _TEST_KEY) -> AuthConfig:
    import jwt as pyjwt

    now = int(time.time())
    worker_token = pyjwt.encode(
        {"sub": "worker", "exp": now + 600, "iss": "undef-terminal", "aud": "undef-terminal-server"},
        key=key,
        algorithm="HS256",
    )
    return AuthConfig(
        mode="jwt",
        jwt_public_key_pem=key,
        jwt_algorithms=["HS256"],
        jwt_issuer="undef-terminal",
        jwt_audience="undef-terminal-server",
        worker_bearer_token=worker_token,
    )


def _make_jwt_token(
    sub: str = "user1",
    roles: Any = None,
    exp_offset: int = 600,
    key: str = _TEST_KEY,
) -> str:
    import jwt as pyjwt

    if roles is None:
        roles = ["operator"]
    now = int(time.time())
    payload = {
        "sub": sub,
        "roles": roles,
        "iss": "undef-terminal",
        "aud": "undef-terminal-server",
        "iat": now,
        "nbf": now,
        "exp": now + exp_offset,
    }
    return pyjwt.encode(payload, key=key, algorithm="HS256")


# ===========================================================================
# auth.py — _anonymous_principal()
# ===========================================================================


class TestAnonymousPrincipal:
    def test_anonymous_has_scopes_frozenset(self) -> None:
        """mutmut_3: scopes=None; mutmut_6: scopes omitted."""
        from undef.terminal.server.auth import _anonymous_principal

        p = _anonymous_principal()
        assert p.scopes is not None
        assert isinstance(p.scopes, frozenset)
        assert len(p.scopes) == 0

    def test_anonymous_subject_id(self) -> None:
        from undef.terminal.server.auth import _anonymous_principal

        p = _anonymous_principal()
        assert p.subject_id == "anonymous"

    def test_anonymous_has_viewer_role(self) -> None:
        from undef.terminal.server.auth import _anonymous_principal

        p = _anonymous_principal()
        assert "viewer" in p.roles


# ===========================================================================
# auth.py — _principal_from_header_auth()
# ===========================================================================


class TestPrincipalFromHeaderAuth:
    def _auth(self) -> AuthConfig:
        return AuthConfig(
            mode="header",
            worker_bearer_token=_make_jwt_token(),
        )

    def test_no_role_header_defaults_to_viewer(self) -> None:
        """mutmut_15/17/18: role default changed — empty string should still give viewer."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1"}, {}, auth)
        assert "viewer" in p.roles

    def test_role_header_viewer_accepted(self) -> None:
        """mutmut_22/23: 'viewer' mutated in valid roles set."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "viewer"}, {}, auth)
        assert "viewer" in p.roles

    def test_role_header_operator_accepted(self) -> None:
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "operator"}, {}, auth)
        assert "operator" in p.roles

    def test_role_header_admin_accepted(self) -> None:
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "admin"}, {}, auth)
        assert "admin" in p.roles

    def test_invalid_role_falls_back_to_viewer(self) -> None:
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "superadmin"}, {}, auth)
        assert p.roles == frozenset({"viewer"})

    def test_scopes_is_frozenset(self) -> None:
        """mutmut_33/36: scopes=None or omitted."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1"}, {}, auth)
        assert isinstance(p.scopes, frozenset)

    def test_no_role_header_with_non_empty_default_would_be_invalid(self) -> None:
        """mutmut_18: default 'XXXX' would give invalid role, falling back to viewer."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        # No role header — must default to viewer (not some garbage role)
        p = _principal_from_header_auth({}, {}, auth)
        assert p.roles == frozenset({"viewer"})


# ===========================================================================
# auth.py — _principal_from_local_mode()
# ===========================================================================


class TestPrincipalFromLocalMode:
    def _auth(self) -> AuthConfig:
        return AuthConfig(
            mode="dev",
            worker_bearer_token=_make_jwt_token(),
        )

    def test_no_header_defaults_to_local_dev(self) -> None:
        """mutmut_9/10: default changed to XXlocal-devXX or LOCAL-DEV."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({}, {}, auth)
        assert p.subject_id == "local-dev"

    def test_cookie_fallback_used(self) -> None:
        """mutmut_6: _cookie_value(cookies, None) instead of (cookies, auth.principal_cookie)."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        cookies = {"uterm_principal": "cookie-user"}
        p = _principal_from_local_mode({}, cookies, auth)
        assert p.subject_id == "cookie-user"

    def test_or_semantics_not_and(self) -> None:
        """mutmut_2: 'or' changed to 'and' in fallback chain."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        # No headers, no cookies — should fall back to "local-dev"
        p = _principal_from_local_mode({}, {}, auth)
        assert p.subject_id == "local-dev"

    def test_no_role_defaults_to_admin(self) -> None:
        """mutmut_15/17/18: role default changed."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({}, {}, auth)
        assert "admin" in p.roles

    def test_role_header_viewer_accepted(self) -> None:
        """mutmut_24 doesn't affect viewer — but let's test all 3."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({"x-uterm-role": "viewer"}, {}, auth)
        assert "viewer" in p.roles

    def test_role_header_operator_accepted(self) -> None:
        """mutmut_24/25: 'operator' mutated in valid roles set."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({"x-uterm-role": "operator"}, {}, auth)
        assert "operator" in p.roles

    def test_role_header_admin_accepted(self) -> None:
        """mutmut_26/27: 'admin' mutated in valid roles set."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({"x-uterm-role": "admin"}, {}, auth)
        assert "admin" in p.roles

    def test_scopes_includes_wildcard(self) -> None:
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({}, {}, auth)
        assert "*" in p.scopes


# ===========================================================================
# auth.py — _resolve_principal()
# ===========================================================================


class TestResolvePrincipal:
    def test_header_mode_passes_cookies(self) -> None:
        """mutmut_19: _principal_from_header_auth(headers, None, auth) — cookies lost."""
        from undef.terminal.server.auth import _resolve_principal

        auth = AuthConfig(
            mode="header",
            worker_bearer_token=_make_jwt_token(),
        )
        cookies = {"uterm_principal": "cookie-user"}
        p = _resolve_principal({}, cookies, auth)
        assert p.subject_id == "cookie-user"

    def test_jwt_failure_logs_and_returns_anonymous(self) -> None:
        """mutmut_41/42/43/44: logger.warning args mutated — exception must still be caught."""
        from undef.terminal.server.auth import _resolve_principal

        auth = AuthConfig(
            mode="jwt",
            jwt_public_key_pem=_TEST_KEY,
            jwt_algorithms=["HS256"],
            jwt_issuer="undef-terminal",
            jwt_audience="undef-terminal-server",
            worker_bearer_token=_make_jwt_token(),
        )
        headers = {"authorization": "Bearer INVALID_TOKEN"}
        p = _resolve_principal(headers, {}, auth)
        assert p.subject_id == "anonymous"

    def test_jwt_failure_logged_as_warning(self) -> None:
        """mutmut_41/42/43/44: verify logger.warning is called (not swallowed)."""
        from undef.terminal.server.auth import _resolve_principal

        auth = AuthConfig(
            mode="jwt",
            jwt_public_key_pem=_TEST_KEY,
            jwt_algorithms=["HS256"],
            jwt_issuer="undef-terminal",
            jwt_audience="undef-terminal-server",
            worker_bearer_token=_make_jwt_token(),
        )
        headers = {"authorization": "Bearer INVALID_TOKEN"}
        with patch("undef.terminal.server.auth.logger") as mock_logger:
            _resolve_principal(headers, {}, auth)
        mock_logger.warning.assert_called_once()


# ===========================================================================
# auth.py — resolve_http_principal() / resolve_ws_principal()
# ===========================================================================


class TestResolveHttpPrincipal:
    def test_uses_request_headers(self) -> None:
        """mutmut_4/7: headers default changed to None/nothing."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeRequest:
            headers = {"x-uterm-principal": "req-user"}
            cookies: dict[str, str] = {}

        p = resolve_http_principal(_FakeRequest(), auth)
        assert p.subject_id == "req-user"

    def test_no_headers_attribute_falls_back(self) -> None:
        """mutmut_4: getattr with default None — code calling .get() on None would fail."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())
        # object with no headers attr — should use default {}
        p = resolve_http_principal(object(), auth)
        assert p is not None

    def test_uses_request_cookies(self) -> None:
        """mutmut_13/16: cookies default changed to None/nothing."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeRequest:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "cookie-user"}

        p = resolve_http_principal(_FakeRequest(), auth)
        assert p.subject_id == "cookie-user"

    def test_no_cookies_attribute_falls_back(self) -> None:
        """mutmut_13: getattr(req, cookies, None) — None.get() would fail."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeRequest:
            headers: dict[str, str] = {}
            # no cookies attr

        p = resolve_http_principal(_FakeRequest(), auth)
        assert p is not None


class TestResolveWsPrincipal:
    def test_uses_websocket_headers(self) -> None:
        """mutmut_4/7: headers default None/nothing."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers = {"x-uterm-principal": "ws-user"}
            cookies: dict[str, str] = {}

        p = resolve_ws_principal(_FakeWsObj(), auth)
        assert p.subject_id == "ws-user"

    def test_no_headers_attribute_falls_back(self) -> None:
        """mutmut_4: default None breaks subsequent .get() call."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())
        p = resolve_ws_principal(object(), auth)
        assert p is not None

    def test_uses_websocket_cookies(self) -> None:
        """mutmut_11/13/16: cookies source/default mutated."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "ws-cookie-user"}

        p = resolve_ws_principal(_FakeWsObj(), auth)
        assert p.subject_id == "ws-cookie-user"

    def test_uses_correct_cookies_attr_name(self) -> None:
        """mutmut_17/18: 'cookies' attr name changed to 'XXcookiesXX' or 'COOKIES'."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "right-user"}
            # purposely NOT providing XXcookiesXX or COOKIES

        p = resolve_ws_principal(_FakeWsObj(), auth)
        assert p.subject_id == "right-user"

    def test_uses_websocket_not_none_for_cookies(self) -> None:
        """mutmut_11: getattr(None, 'cookies', {}) instead of getattr(websocket,...)."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "ws-user"}

        p = resolve_ws_principal(_FakeWsObj(), auth)
        # Must pick up cookie from the actual websocket object
        assert p.subject_id == "ws-user"
