#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Minimal conftest for tests_mutation/ — mutation-killing test suite.

This directory is outside testpaths so normal `uv run pytest` never discovers
it. mutmut's tests_dir includes it so these tests run during mutation campaigns.
"""
