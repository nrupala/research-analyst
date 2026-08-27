"""Slice A.3d: per-ticker currency in the comparative report renderer.

USD/None stays byte-identical ("$"); a non-USD ticker localises its price cell
(INR -> the rupee symbol). Pure and offline.
"""
from datetime import datetime, timezone

from research_analyst.comparative import (
    ComparativeReport,
    DimensionComparison,
    MetricComparison,
    build_comparative_report,
)
from research_analyst.enums import SecurityType
from research_analyst.models import ResearchMetadata, ResearchResponse
from research_analyst.reports.comparative_renderer import render_html, render_markdown


def _price_metric(values):
    return MetricComparison(
        key="current_price", label="Current price", dimension="Valuation",
        unit="price", higher_is_better=True, rankable=False, source="test",
        available=True, values=values,
    )


def _report(tickers, currencies, values):
    return ComparativeReport(
        requested_tickers=tickers,
        tickers=tickers,
        company_names={t: t for t in tickers},
        currencies=currencies,
        generated_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        dimensions=[DimensionComparison(name="Valuation", metrics=[_price_metric(values)])],
    )


def test_comparative_renders_per_ticker_currency_md_and_html():
    rpt = _report(
        ["AAPL", "RELIANCE.NS"],
        {"AAPL": "USD", "RELIANCE.NS": "INR"},
        {"AAPL": 230.0, "RELIANCE.NS": 1450.5},
    )
    md = render_markdown(rpt)
    html_out = render_html(rpt)
    assert "$230.00" in md
    assert "\u20b91,450.50" in md
    assert "$230.00" in html_out
    assert "\u20b91,450.50" in html_out


def test_comparative_us_only_is_dollar_only():
    rpt = _report(
        ["AAPL", "MSFT"],
        {"AAPL": "USD", "MSFT": "USD"},
        {"AAPL": 230.0, "MSFT": 410.25},
    )
    md = render_markdown(rpt)
    assert "$230.00" in md and "$410.25" in md
    assert "\u20b9" not in md


def _resp(ticker, currency):
    return ResearchResponse(
        ticker=ticker,
        security_type=SecurityType.EQUITY,
        company_name=ticker,
        currency=currency,
        generated_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        reports=[],
        metadata=ResearchMetadata(),
    )


def test_build_comparative_report_maps_currency():
    rpt = build_comparative_report([_resp("AAPL", "USD"), _resp("RELIANCE.NS", "INR")])
    assert rpt.currencies == {"AAPL": "USD", "RELIANCE.NS": "INR"}
