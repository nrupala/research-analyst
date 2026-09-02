"""CLI entry point — run research from the command line or start the web server.

Usage:
  # Start web server
  research-analyst serve

  # Run research from CLI
  research-analyst research AAPL
  research-analyst research AAPL --report-type all
  research-analyst research AAPL --report-type tactical --timeframe 3M

  # Health check
  research-analyst health
"""
# Module: research_analyst/cli.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import settings


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="research-analyst",
        description="Research Analyst — Institutional-grade equity and ETF research agent.",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- serve ---
    serve_parser = subparsers.add_parser("serve", help="Start the web server.")
    serve_parser.add_argument("--host", default=settings.server.host, help="Bind host.")
    serve_parser.add_argument("--port", type=int, default=settings.server.port, help="Bind port.")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload.")

    # --- research ---
    research_parser = subparsers.add_parser("research", help="Run research for a ticker.")
    research_parser.add_argument("ticker", help="Ticker symbol (e.g., AAPL, SPY).")
    research_parser.add_argument(
        "--report-type", "-r", default=None,
        help="Report type: long_term, tactical, comprehensive, or all. Default: comprehensive.",
    )
    research_parser.add_argument(
        "--timeframe", "-t", default="1Y",
        help="Analysis timeframe: 1M, 3M, 6M, 1Y, 3Y, 5Y, 10Y. Default: 1Y.",
    )
    research_parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path. Default: stdout (Markdown) or {ticker}_report.md.",
    )
    research_parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of Markdown.",
    )

    # --- resolve ---
    resolve_parser = subparsers.add_parser(
        "resolve", help="Resolve a company name or symbol to a ticker."
    )
    resolve_parser.add_argument(
        "query", help=('Company name or symbol (e.g., "Reliance Industries" or RELIANCE.NS).')
    )

    # --- health ---
    subparsers.add_parser("health", help="Check system health.")

    # --- schema-export ---
    schema_parser = subparsers.add_parser(
        "schema-export",
        help="Emit typed-export artifacts (JSON Schema + TypeScript .d.ts) to an output dir.",
    )
    schema_parser.add_argument(
        "--out", "-o", default="exports",
        help="Output directory (default: ./exports).",
    )

    # --- sync ---
    sync_parser = subparsers.add_parser(
        "sync",
        help="Local-first batch export: pull structured bundles for a watchlist into a local sink.",
    )
    sync_parser.add_argument("watchlist", help="Path to a watchlist JSON file ({tickers: [...]}).")
    sync_parser.add_argument(
        "--out", "-o", default="data",
        help="Output directory for the SQLite sink + NDJSON bundles (default: ./data).",
    )
    sync_parser.add_argument(
        "--max-age-hours", type=float, default=24.0,
        help="Skip tickers synced within this many hours (incremental; default 24).",
    )

    # --- tui ---
    from .tui import add_tui_parser
    add_tui_parser(subparsers)

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "research":
        asyncio.run(_cmd_research(args))
    elif args.command == "resolve":
        asyncio.run(_cmd_resolve(args))
    elif args.command == "health":
        _cmd_health()
    elif args.command == "schema-export":
        _cmd_schema_export(args)
    elif args.command == "sync":
        _cmd_sync(args)
    elif args.command == "tui":
        from .tui import run_tui_command

        run_tui_command(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI web server."""
    import uvicorn

    settings.ensure_dirs()

    print(f"Starting Research Analyst server on http://{args.host}:{args.port}")
    print(f"API docs: http://{args.host}:{args.port}/api/docs")
    print(f"Browser UI: http://{args.host}:{args.port}/")

    uvicorn.run(
        "research_analyst.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


async def _cmd_research(args: argparse.Namespace) -> None:
    """Run research from CLI."""
    from .enums import ReportType, Timeframe
    from .models import ResearchRequest
    from .orchestrator import ResearchOrchestrator

    settings.ensure_dirs()

    # Parse report types
    report_types = ReportType.from_user_input(args.report_type)

    # Parse timeframe
    timeframe_map = {
        "1M": Timeframe.ONE_MONTH, "3M": Timeframe.THREE_MONTHS,
        "6M": Timeframe.SIX_MONTHS, "1Y": Timeframe.ONE_YEAR,
        "3Y": Timeframe.THREE_YEARS, "5Y": Timeframe.FIVE_YEARS,
        "10Y": Timeframe.TEN_YEARS,
    }
    timeframe = timeframe_map.get(args.timeframe.upper(), Timeframe.ONE_YEAR)

    request = ResearchRequest(
        ticker=args.ticker.upper().strip(),
        report_types=report_types,
        timeframe=timeframe,
    )

    print(f"Running research for {request.ticker}...")
    print(f"Report types: {', '.join(r.value for r in report_types)}")
    print(f"Timeframe: {timeframe.value}")
    print()

    orchestrator = ResearchOrchestrator()
    try:
        response = await orchestrator.run(request)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.json:
        output = response.model_dump_json(indent=2)
    else:
        parts: list[str] = []
        for report in response.reports:
            parts.append(report.to_markdown())
            parts.append("\n\n---\n\n")
        output = "\n".join(parts)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output)
        print(f"Report written to {output_path}")
    else:
        print(output)

    # Summary
    meta = response.metadata
    print("\n--- Research Complete ---")
    print(f"Ticker: {response.ticker} ({response.company_name})")
    print(f"Reports generated: {len(response.reports)}")
    print(f"Processing time: {meta.processing_time_seconds:.1f}s")
    print(f"Data sources: {', '.join(meta.data_sources)}")
    if meta.warnings:
        print(f"Warnings: {len(meta.warnings)}")
        for w in meta.warnings:
            print(f"  - {w}")


async def _cmd_resolve(args: argparse.Namespace) -> None:
    """Resolve a company name or symbol to a ticker (safe-confirm)."""
    from .providers.market_data import MarketDataProvider
    from .resolver import resolve_subject

    provider = MarketDataProvider()
    matches = await provider.search_symbols(args.query)
    res = resolve_subject(args.query, matches)

    if res.status == "resolved" and res.resolved:
        r = res.resolved
        label = " - ".join(x for x in (r.name, r.market_name, r.currency) if x)
        print(f"Resolved: {r.symbol}" + (f"  ({label})" if label else ""))
        print(f"Run: research-analyst research {r.symbol}")
    elif res.status == "ambiguous":
        print(f"Multiple listings match '{args.query}' -- pick one and re-run with its symbol:")
        for c in res.candidates:
            meta = " - ".join(x for x in (c.market_name, c.currency, c.quote_type) if x)
            print(f"  {c.symbol:<14} {c.name}" + (f"  [{meta}]" if meta else ""))
    else:
        print(f"No listed equity or ETF found for '{args.query}'.", file=sys.stderr)
        sys.exit(1)


def _cmd_health() -> None:
    """Print health status."""
    print("Research Analyst v0.1.0")
    print("Config: OK")
    print(f"Output dir: {settings.output_dir}")
    print(f"Cache dir: {settings.market.cache_dir}")
    print(f"Server port: {settings.server.port}")
    print("Status: HEALTHY")


def _cmd_schema_export(args: argparse.Namespace) -> None:
    """Emit typed-export artifacts (JSON Schema + TypeScript .d.ts)."""
    import json as _json

    from .api_models import SCHEMA_VERSION
    from .exporters import json_schemas_all, ts_definitions

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, schema in json_schemas_all().items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(_json.dumps(schema, indent=2) + "\n")
        print(f"wrote {path}")

    ts_path = out_dir / "types.d.ts"
    ts_path.write_text(ts_definitions())
    print(f"wrote {ts_path}")

    print(f"\nSchema artifacts exported (schema_version={SCHEMA_VERSION}) to {out_dir.resolve()}")


def _cmd_sync(args: argparse.Namespace) -> None:
    """Local-first batch export for a watchlist (SQLite sink + NDJSON bundles)."""
    from pathlib import Path as _Path

    from .sync import run_sync

    watchlist = _Path(args.watchlist)
    out_dir = _Path(args.out)
    result = run_sync(
        watchlist,
        out_dir,
        max_age_hours=args.max_age_hours,
    )
    print("\nSync complete:")
    print(f"  ok      : {len(result.succeeded)}")
    print(f"  skipped : {len(result.skipped_fresh)} (fresh within {args.max_age_hours:g}h)")
    if result.failed:
        print(f"  failed  : {len(result.failed)}")
        for ticker, err in result.failed.items():
            print(f"    - {ticker}: {err}")
    print(f"\nBundles written to {out_dir.resolve()} (bundle.db + *.ndjson)")


if __name__ == "__main__":
    main()
