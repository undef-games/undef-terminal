# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "requires_pam: requires /etc/pam.d/undef-terminal"
    )
    config.addinivalue_line("markers", "requires_root: requires root or CAP_SETUID")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("requires_root") and os.getuid() != 0:
            item.add_marker(pytest.mark.skip(reason="requires root or CAP_SETUID"))
        if (
            item.get_closest_marker("requires_pam")
            and not Path("/etc/pam.d/undef-terminal").exists()
        ):
            item.add_marker(
                pytest.mark.skip(reason="requires /etc/pam.d/undef-terminal")
            )
