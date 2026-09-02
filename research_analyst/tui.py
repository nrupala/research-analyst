"""Terminal surface (Phase 6) — a keyboard-first TUI for Research Analyst.

Built on Textual (pure Python, cross-platform, no Docker, no GUI server).
Two modes:

  * Interactive TUI  — ``research-analyst tui``
      - ticker input, report-type selector, run, scrollable report view,
        export (markdown), and a keyboard-driven workflow (Bloomberg-style).
  * Headless query   — ``research-analyst tui --query AAPL [--report-type X]``
      - renders a report to stdout for scripting/pipelines (fully testable).

The heavy lifting reuses the same orchestrator as the web API; this is a thin,
keyboard-first shell over it.
"""
# Module: research_analyst/tui.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from .enums import ReportType
from .models import ResearchRequest
from .orchestrator import ResearchOrchestrator

# ---------------------------------------------------------------------------
# Headless query (testable, used by both the TUI runner and the CLI)
# ---------------------------------------------------------------------------


def build_request(ticker: str, report_type: str, timeframe: str = "1Y") -> ResearchRequest:
    """Build a typed ResearchRequest from CLI-style strings."""
    from .enums import Timeframe

    tf_map = {
        "1M": Timeframe.ONE_MONTH, "3M": Timeframe.THREE_MONTHS,
        "6M": Timeframe.SIX_MONTHS, "1Y": Timeframe.ONE_YEAR,
        "3Y": Timeframe.THREE_YEARS, "5Y": Timeframe.FIVE_YEARS,
        "10Y": Timeframe.TEN_YEARS,
    }
    return ResearchRequest(
        ticker=ticker.upper().strip(),
        report_types=ReportType.from_user_input(report_type),
        timeframe=tf_map.get(timeframe.upper(), Timeframe.ONE_YEAR),
    )


async def query_report(
    request: ResearchRequest,
    orchestrator: ResearchOrchestrator | None = None,
) -> list[str]:
    """Run a request and return the rendered markdown reports."""
    orch = orchestrator or ResearchOrchestrator()
    result = await orch.run(request)
    return [r.to_markdown() for r in result.reports]


def run_headless(
    ticker: str,
    report_type: str = "comprehensive",
    timeframe: str = "1Y",
    orchestrator: ResearchOrchestrator | None = None,
) -> list[str]:
    """Synchronous headless query (used by the CLI --query mode)."""
    request = build_request(ticker, report_type, timeframe)
    return asyncio.run(query_report(request, orchestrator))


# ---------------------------------------------------------------------------
# Interactive TUI (Textual) — imported lazily so the core stays light
# ---------------------------------------------------------------------------


class ResearchTUI:
    """Thin wrapper so ``tui.py`` imports cleanly without Textual installed
    (the interactive app itself lives in ``tui_app.py``)."""

    @staticmethod
    def available() -> bool:
        try:
            import textual  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def run() -> None:
        if not ResearchTUI.available():
            print(
                "The interactive TUI requires Textual.\n"
                "  pip install research-analyst[tui]  (or: pip install textual)\n"
                "The headless query still works: research-analyst tui --query AAPL",
                file=sys.stderr,
            )
            sys.exit(1)
        from .tui_app import run_app

        run_app()


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def add_tui_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "tui",
        help="Keyboard-first terminal interface (Bloomberg-style).",
    )
    parser.add_argument(
        "--query", "-q", default=None,
        help="Headless mode: ticker to research (renders to stdout, no TUI).",
    )
    parser.add_argument(
        "--report-type", default="comprehensive",
        help="Report type for headless mode (comprehensive | long_term | tactical | all).",
    )
    parser.add_argument(
        "--timeframe", default="1Y",
        help="Timeframe for headless mode (e.g. 1Y, 3Y).",
    )
    return parser


def run_tui_command(args: argparse.Namespace) -> None:
    """Dispatch the tui subcommand (headless or interactive)."""
    if args.query:
        reports = run_headless(args.query, args.report_type, args.timeframe)
        for i, md in enumerate(reports):
            if i:
                print("\n\n" + "=" * 72 + "\n")
            print(md)
        return
    ResearchTUI.run()
