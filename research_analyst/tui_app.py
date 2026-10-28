# Copyright (C) 2026 2351485 ALBERTA INC.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Textual interactive TUI for Research Analyst (Phase 6).

Keyboard-first, Bloomberg-style surface: ticker input, report-type toggle,
run, scrollable report view, and markdown export. Reuses the same
ResearchOrchestrator as the web API.
"""
# Module: research_analyst/tui_app.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Markdown, Select, Static

from .orchestrator import ResearchOrchestrator
from .tui import build_request, query_report

REPORT_TYPES = [
    ("Comprehensive", "comprehensive"),
    ("Long-Term", "long_term"),
    ("Tactical / Near-Term", "tactical"),
    ("All Reports", "all"),
]


class ResearchScreen(Screen):  # type: ignore[misc]  # textual not installed in CI
    """Main screen: input controls on top, scrollable report below."""

    BINDINGS = [
        ("ctrl+r", "run", "Run research"),
        ("ctrl+e", "export", "Export markdown"),
        ("ctrl+q", "app.quit", "Quit"),
        ("ctrl+c", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="controls"):
            yield Label("Research Analyst — Terminal", id="title")
            with Horizontal(id="inputs"):
                yield Input(placeholder="Ticker (e.g. AAPL, RELIANCE.NS, SPY)", id="ticker")
                yield Select(
                    REPORT_TYPES,
                    value="comprehensive",
                    id="report-type",
                    prompt="Report type",
                )
            with Horizontal(id="actions"):
                yield Button("Run (Ctrl+R)", id="run", variant="primary")
                yield Button("Export (Ctrl+E)", id="export", variant="default")
            yield Static("", id="status")
        yield Markdown("", id="report")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#ticker", Input).focus()

    async def action_run(self) -> None:
        await self._run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            asyncio.create_task(self._run())
        elif event.button.id == "export":
            asyncio.create_task(self._export())

    async def _run(self) -> None:
        ticker = self.query_one("#ticker", Input).value.strip()
        if not ticker:
            self.query_one("#status", Static).update("Enter a ticker first.")
            return
        report_type = str(self.query_one("#report-type", Select).value or "comprehensive")
        status = self.query_one("#status", Static)
        status.update(f"Researching {ticker.upper()} ({report_type})…")
        try:
            request = build_request(ticker, report_type)
            reports = await query_report(request, ResearchOrchestrator())
            body = "\n\n---\n\n".join(reports)
            self.query_one("#report", Markdown).update(body)
            status.update(f"{ticker.upper()}: {len(reports)} report(s) ready. Ctrl+E to export.")
        except Exception as e:  # surface errors in the TUI, never crash it
            status.update(f"Error: {type(e).__name__}: {e}")

    async def _export(self) -> None:
        md = self.query_one("#report", Markdown)
        source = getattr(md, "source", "") or ""
        if not source:
            self.query_one("#status", Static).update("Nothing to export yet.")
            return
        path = Path(f"report-{self.query_one('#ticker', Input).value.strip().upper() or 'out'}.md")
        path.write_text(source, encoding="utf-8")
        self.query_one("#status", Static).update(f"Exported to {path.name}")


class ResearchApp(App[None]):  # type: ignore[misc]  # textual not installed in CI
    """The Research Analyst TUI application."""

    TITLE = "Research Analyst"
    SUB_TITLE = "Institutional equity & ETF research — terminal"
    CSS = """
    #controls { padding: 1; border-bottom: solid $primary; }
    #title { text-style: bold; text-color: $primary; margin-bottom: 1; }
    #inputs { height: 3; }
    #ticker { width: 2fr; margin-right: 1; }
    #report-type { width: 1fr; }
    #actions { height: 3; align-horizontal: left; }
    #run { margin-right: 1; }
    #status { color: $text-muted; margin-top: 1; }
    #report { padding: 1 2; }
    """

    def on_mount(self) -> None:
        self.push_screen(ResearchScreen())


def run_app() -> None:
    ResearchApp().run()
