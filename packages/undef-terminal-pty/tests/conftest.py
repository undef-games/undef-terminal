# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
from pathlib import Path

import pytest

# pamela 1.2.0's ctypes PAM conversation callback is incompatible with Python 3.12+.
# It segfaults inside pam_authenticate() on all calls. Python 3.11 works correctly.
_PAMELA_BROKEN = sys.version_info >= (3, 12)

# Docker containers have /.dockerenv; pam_unix.so's unix_chkpwd setuid helper
# hangs indefinitely on wrong credentials inside Docker, so we skip tests
# that require PAM authentication failure in that environment.
_IN_DOCKER = Path("/.dockerenv").exists()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "requires_pam: requires /etc/pam.d/undef-terminal"
    )
    config.addinivalue_line(
        "markers",
        "requires_pam_auth: requires /etc/pam.d/undef-terminal with working auth "
        "(skipped in Docker — unix_chkpwd hangs on wrong credentials)",
    )
    config.addinivalue_line("markers", "requires_root: requires root or CAP_SETUID")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    pam_svc = Path("/etc/pam.d/undef-terminal")
    for item in items:
        if item.get_closest_marker("requires_root") and os.getuid() != 0:
            item.add_marker(pytest.mark.skip(reason="requires root or CAP_SETUID"))
        if item.get_closest_marker("requires_pam") and (
            not pam_svc.exists() or _PAMELA_BROKEN
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "requires /etc/pam.d/undef-terminal and pamela-compatible "
                        "Python (pamela 1.2.0 segfaults on Python 3.12+)"
                    )
                )
            )
        if item.get_closest_marker("requires_pam_auth") and (
            not pam_svc.exists() or _IN_DOCKER or _PAMELA_BROKEN
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "requires /etc/pam.d/undef-terminal with working unix_chkpwd "
                        "and pamela-compatible Python (skipped in Docker/Python 3.12+)"
                    )
                )
            )
