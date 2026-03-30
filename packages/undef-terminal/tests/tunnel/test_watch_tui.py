#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Textual TUI tests for uterm watch using App.run_test()."""

from __future__ import annotations

import pytest

from undef.terminal.cli._watch_app import Exchange, WatchApp, _detail_lines


@pytest.fixture
def app() -> WatchApp:
    """Create a WatchApp that won't try to connect a real WebSocket."""
    return WatchApp(
        ws_url="ws://localhost:9999/ws/browser/test/term", tunnel_id="test-tui", initial_layout="horizontal"
    )


class TestWatchAppRenders:
    @pytest.mark.asyncio
    async def test_app_mounts_widgets(self, app: WatchApp) -> None:
        """App renders DataTable, detail pane, status bar, header, footer."""
        async with app.run_test(size=(120, 40)) as _pilot:
            assert app.query_one("#request-table") is not None
            assert app.query_one("#detail-pane") is not None
            assert app.query_one("#status-bar") is not None

    @pytest.mark.asyncio
    async def test_table_has_columns(self, app: WatchApp) -> None:
        """DataTable has the expected columns."""
        from textual.widgets import DataTable

        async with app.run_test(size=(120, 40)) as _pilot:
            table = app.query_one("#request-table", DataTable)
            col_labels = [str(c.label) for c in table.columns.values()]
            assert "Method" in col_labels
            assert "URL" in col_labels
            assert "Status" in col_labels
            assert "Duration" in col_labels
            assert "Size" in col_labels

    @pytest.mark.asyncio
    async def test_handle_http_req_adds_row(self, app: WatchApp) -> None:
        """_handle_frame with http_req adds a row to the table."""
        from textual.widgets import DataTable

        async with app.run_test(size=(120, 40)) as _pilot:
            app._handle_frame(
                {
                    "type": "http_req",
                    "id": "r1",
                    "method": "GET",
                    "url": "/api/test",
                    "headers": {"accept": "application/json"},
                    "body_size": 0,
                }
            )
            table = app.query_one("#request-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_handle_http_res_updates_row(self, app: WatchApp) -> None:
        """_handle_frame with http_res updates the matching row."""
        async with app.run_test(size=(120, 40)) as _pilot:
            app._handle_frame(
                {
                    "type": "http_req",
                    "id": "r1",
                    "method": "POST",
                    "url": "/api/login",
                    "headers": {},
                    "body_size": 10,
                }
            )
            app._handle_frame(
                {
                    "type": "http_res",
                    "id": "r1",
                    "status": 200,
                    "status_text": "OK",
                    "headers": {},
                    "body_size": 24,
                    "duration_ms": 89,
                }
            )
            assert app._exchanges[0].status == 200
            assert app._exchanges[0].duration_ms == 89

    @pytest.mark.asyncio
    async def test_multiple_exchanges(self, app: WatchApp) -> None:
        """Multiple request/response pairs tracked correctly."""
        from textual.widgets import DataTable

        async with app.run_test(size=(120, 40)) as _pilot:
            for i in range(5):
                app._handle_frame(
                    {
                        "type": "http_req",
                        "id": f"r{i}",
                        "method": "GET",
                        "url": f"/api/item/{i}",
                        "headers": {},
                        "body_size": 0,
                    }
                )
                app._handle_frame(
                    {
                        "type": "http_res",
                        "id": f"r{i}",
                        "status": 200,
                        "status_text": "OK",
                        "headers": {},
                        "body_size": 10,
                        "duration_ms": i + 1.0,
                    }
                )
            table = app.query_one("#request-table", DataTable)
            assert table.row_count == 5
            assert len(app._exchanges) == 5


class TestWatchAppActions:
    @pytest.mark.asyncio
    async def test_cycle_layout(self, app: WatchApp) -> None:
        """Tab cycles through layout modes."""
        async with app.run_test(size=(120, 40)) as pilot:
            assert app._layout_mode == "horizontal"
            await pilot.press("l")
            assert app._layout_mode == "vertical"
            await pilot.press("l")
            assert app._layout_mode == "modal"
            await pilot.press("l")
            assert app._layout_mode == "horizontal"

    @pytest.mark.asyncio
    async def test_cycle_method_filter(self, app: WatchApp) -> None:
        """f cycles through method filters."""
        async with app.run_test(size=(120, 40)) as pilot:
            assert app._method_filter == ""
            await pilot.press("f")
            assert app._method_filter == "GET"
            await pilot.press("f")
            assert app._method_filter == "POST"

    @pytest.mark.asyncio
    async def test_method_filter_hides_rows(self, app: WatchApp) -> None:
        """Method filter hides non-matching rows on rebuild."""
        from textual.widgets import DataTable

        async with app.run_test(size=(120, 40)) as _pilot:
            app._handle_frame(
                {"type": "http_req", "id": "r1", "method": "GET", "url": "/a", "headers": {}, "body_size": 0}
            )
            app._handle_frame(
                {"type": "http_req", "id": "r2", "method": "POST", "url": "/b", "headers": {}, "body_size": 0}
            )
            table = app.query_one("#request-table", DataTable)
            assert table.row_count == 2

            app._method_filter = "GET"
            app._rebuild_table()
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_quit(self, app: WatchApp) -> None:
        """q quits the app."""
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("q")


class TestDetailLines:
    def test_request_only(self) -> None:
        ex = Exchange(req_id="r1", method="GET", url="/api/test", req_headers={"accept": "text/html"})
        lines = _detail_lines(ex)
        assert any("GET /api/test" in line for line in lines)
        assert any("accept" in line for line in lines)

    def test_with_response(self) -> None:
        ex = Exchange(
            req_id="r1",
            method="POST",
            url="/api/login",
            req_headers={"content-type": "application/json"},
            status=200,
            status_text="OK",
            duration_ms=89,
            res_headers={"x-request-id": "r1"},
        )
        lines = _detail_lines(ex)
        assert any("200" in line for line in lines)
        assert any("x-request-id" in line for line in lines)
