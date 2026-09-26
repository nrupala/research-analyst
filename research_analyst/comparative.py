# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
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

"""Comparative analysis — multi-ticker side-by-side research reports (v0.2.0).

This module is strictly ADDITIVE. It runs the EXISTING single-ticker pipeline
(:meth:`ResearchOrchestrator.run`) once per ticker and layers a cross-ticker
comparison on top. It never modifies the single-ticker path or its models.

Design
------
* :class:`ComparativeOrchestrator` ``run(tickers)`` -> :class:`ComparativeReport`
    - validates 2-5 distinct tickers (rejects otherwise with ``ValueError``)
    - runs the existing orchestrator once per ticker (bounded concurrency)
    - an invalid / unresolvable ticker is skipped with a recorded error, never
      crashing the whole request (no-lockout rule)
* :func:`build_comparative_report` is a PURE function over per-ticker
  :class:`ResearchResponse` objects -> :class:`ComparativeReport`
  (fully unit-testable, no I/O).
* :func:`rank_metric` is the PURE ranking / normalization primitive.

Framing / compliance rule
-------------------------
The tool ranks and compares numbers; the user decides. No buy / sell / hold and
no advice. Every displayed number is traceable back to the exact per-ticker
report field it was carried from, plus that ticker's declared data sources.
"""
# Module: research_analyst/comparative.py | Version: 0.2.0 | Updated: 2026-07-18

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .enums import ReportType, ScenarioType, Timeframe
from .models import ReportOutput, ResearchRequest, ResearchResponse, SourceRecord

logger = logging.getLogger(__name__)

MIN_TICKERS = 2
MAX_TICKERS = 5
_DEFAULT_CONCURRENCY = 3

# Dimension names (order = render order)
DIM_VALUATION = "Valuation"
DIM_GROWTH = "Growth & Margins"
DIM_QUALITY = "Profitability & Capital Quality"
DIM_DIVIDEND = "Dividend & Income"
DIM_RISK = "Risk"
DIMENSION_ORDER = [DIM_VALUATION, DIM_GROWTH, DIM_QUALITY, DIM_DIVIDEND, DIM_RISK]

# Dimensions the single-ticker pipeline computes but only renders as narrative
# (no structured, cross-ticker-comparable fields on ReportOutput yet). Surfacing
# them would require persisting engine outputs on the per-ticker report model,
# which is deliberately out of scope for this backend slice (keeps the
# single-ticker path untouched). Documented, never silently faked.
DEFERRED_DIMENSIONS = ["Technical / Momentum", "Macro / Sector"]

from .disclaimer import DISCLAIMER_SHORT
_DISCLAIMER = DISCLAIMER_SHORT
_COMPLIANCE_NOTE = (
    "This tool ranks and compares numbers; you decide. It makes no buy, sell, or "
    "hold recommendation. The rankings show how the selected tickers compare on "
    "each metric and what would have to be true for the ranking to change — not "
    "what to do."
)


# ---------------------------------------------------------------------------
# Metric registry — declarative extraction from a per-ticker ReportOutput
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricSpec:
    """Declarative spec for a single comparable metric.

    ``extract`` pulls a raw numeric value from a comprehensive
    :class:`ReportOutput`, or ``None`` when unavailable. Missing data is skipped,
    never invented.
    """

    key: str
    label: str
    dimension: str
    higher_is_better: bool
    unit: str                       # "pct" | "ratio" | "score" | "price" | "num"
    source: str                     # provenance: the report field it came from
    extract: Callable[[ReportOutput], float | None]
    rankable: bool = True           # informational-only metrics are not ranked


def _base_scenario(report: ReportOutput):
    """Return the BASE valuation scenario if present, else None."""
    val = report.valuation
    if not val or not val.scenarios:
        return None
    for scenario in val.scenarios:
        if scenario.scenario_type == ScenarioType.BASE:
            return scenario
    return None


def _val_current_price(r: ReportOutput) -> float | None:
    return r.valuation.current_price if r.valuation else None


def _val_base_upside(r: ReportOutput) -> float | None:
    scenario = _base_scenario(r)
    if scenario is None:
        return None
    parts = [v for v in (scenario.implied_upside_low, scenario.implied_upside_high) if v is not None]
    return sum(parts) / len(parts) if parts else None


def _fun_base_rev_growth(r: ReportOutput) -> float | None:
    scenario = _base_scenario(r)
    return scenario.revenue_growth if scenario else None


def _fun_base_op_margin(r: ReportOutput) -> float | None:
    scenario = _base_scenario(r)
    return scenario.operating_margin if scenario else None


def _cap_roic(r: ReportOutput) -> float | None:
    return r.capital_allocation.roic if r.capital_allocation else None


def _cap_roic_minus_wacc(r: ReportOutput) -> float | None:
    return r.capital_allocation.roic_minus_wacc if r.capital_allocation else None


def _cap_shareholder_yield(r: ReportOutput) -> float | None:
    return r.capital_allocation.shareholder_yield if r.capital_allocation else None


def _div_current_yield(r: ReportOutput) -> float | None:
    return r.dividend.current_yield if r.dividend else None


def _div_payout_fcf(r: ReportOutput) -> float | None:
    return r.dividend.payout_ratio_fcf if r.dividend else None


def _div_safety(r: ReportOutput) -> float | None:
    return r.dividend.safety_score if r.dividend else None


def _div_growth_5y(r: ReportOutput) -> float | None:
    return r.dividend.dividend_growth_5y_cagr if r.dividend else None


def _risk_score(r: ReportOutput) -> float | None:
    return r.risk_matrix.overall_risk_score if r.risk_matrix else None


# NB: P/E is intentionally NOT a metric here — ValuationScenario.pe_multiple is
# always None on the model (the multiple is only recorded in assumption text),
# so it is not a structured, provenance-safe field to rank on.
METRIC_REGISTRY: list[MetricSpec] = [
    MetricSpec("current_price", "Current price", DIM_VALUATION, True, "price",
               "per-ticker report -> valuation.current_price", _val_current_price, rankable=False),
    MetricSpec("upside_base", "Base-case implied upside", DIM_VALUATION, True, "pct",
               "per-ticker report -> valuation base scenario implied_upside_low/high (midpoint)",
               _val_base_upside),
    MetricSpec("rev_growth_base", "Revenue growth (base case)", DIM_GROWTH, True, "pct",
               "per-ticker report -> valuation base scenario revenue_growth", _fun_base_rev_growth),
    MetricSpec("op_margin_base", "Operating margin (base case)", DIM_GROWTH, True, "pct",
               "per-ticker report -> valuation base scenario operating_margin", _fun_base_op_margin),
    MetricSpec("roic", "ROIC", DIM_QUALITY, True, "pct",
               "per-ticker report -> capital_allocation.roic", _cap_roic),
    MetricSpec("roic_minus_wacc", "ROIC − WACC spread", DIM_QUALITY, True, "pct",
               "per-ticker report -> capital_allocation.roic_minus_wacc", _cap_roic_minus_wacc),
    MetricSpec("shareholder_yield", "Shareholder yield", DIM_QUALITY, True, "pct",
               "per-ticker report -> capital_allocation.shareholder_yield", _cap_shareholder_yield),
    MetricSpec("div_yield", "Forward dividend yield", DIM_DIVIDEND, True, "pct",
               "per-ticker report -> dividend.current_yield", _div_current_yield),
    MetricSpec("payout_fcf", "Payout ratio (FCF)", DIM_DIVIDEND, False, "pct",
               "per-ticker report -> dividend.payout_ratio_fcf", _div_payout_fcf),
    MetricSpec("div_safety", "Dividend safety score", DIM_DIVIDEND, True, "score",
               "per-ticker report -> dividend.safety_score", _div_safety),
    MetricSpec("div_growth_5y", "Dividend growth (5Y CAGR)", DIM_DIVIDEND, True, "pct",
               "per-ticker report -> dividend.dividend_growth_5y_cagr", _div_growth_5y),
    MetricSpec("risk_score", "Overall risk score (1-10)", DIM_RISK, False, "num",
               "per-ticker report -> risk_matrix.overall_risk_score", _risk_score),
]


# ---------------------------------------------------------------------------
# Ranking / normalization primitive (pure, deterministic)
# ---------------------------------------------------------------------------

@dataclass
class RankResult:
    """Per-ticker ranking outcome for one metric."""

    value: float | None
    percentile: float | None      # 0-100, higher = better
    normalized: float | None      # 0-100 min-max, higher = better
    rank: int | None              # 1 = best; dense ranking (ties share a rank)
    is_winner: bool               # best value in the set (ties -> multiple winners)


def rank_metric(
    values: dict[str, float | None],
    higher_is_better: bool,
) -> dict[str, RankResult]:
    """Rank a single metric across a set of tickers.

    * ``None`` values are treated as "no data": they receive an empty result and
      never influence the ranking of the tickers that do have data.
    * ``percentile`` = share of the *other* tickers with data that this ticker is
      at least as good as (best -> 100, strictly worst -> 0; ties share the top).
    * ``normalized`` = min-max scaled to 0-100, oriented so higher is always
      better. When every value is equal the metric is undifferentiated and all
      get 100.
    """
    valid = {t: v for t, v in values.items() if v is not None}
    if not valid:
        return {t: RankResult(None, None, None, None, False) for t in values}

    vals = list(valid.values())
    best = max(vals) if higher_is_better else min(vals)
    lo, hi = min(vals), max(vals)
    span = hi - lo
    m = len(valid)

    # Dense ranks over distinct values, best first.
    distinct = sorted(set(vals), reverse=higher_is_better)
    rank_of = {val: i + 1 for i, val in enumerate(distinct)}

    out: dict[str, RankResult] = {}
    for t, v in values.items():
        if v is None:
            out[t] = RankResult(None, None, None, None, False)
            continue

        if m == 1:
            pct = 100.0
        else:
            if higher_is_better:
                worse_or_equal = sum(1 for ot, ov in valid.items() if ot != t and ov <= v)
            else:
                worse_or_equal = sum(1 for ot, ov in valid.items() if ot != t and ov >= v)
            pct = worse_or_equal / (m - 1) * 100.0

        if span == 0:
            norm = 100.0
        elif higher_is_better:
            norm = (v - lo) / span * 100.0
        else:
            norm = (hi - v) / span * 100.0

        out[t] = RankResult(
            value=float(v),
            percentile=round(pct, 1),
            normalized=round(norm, 1),
            rank=rank_of[v],
            is_winner=(v == best),
        )
    return out


# ---------------------------------------------------------------------------
# Comparative report models
# ---------------------------------------------------------------------------

class MetricComparison(BaseModel):
    """One metric aligned across every ticker in the set."""

    key: str
    label: str
    dimension: str
    unit: str
    higher_is_better: bool
    rankable: bool
    source: str
    available: bool = False
    values: dict[str, float | None] = Field(default_factory=dict)
    normalized: dict[str, float | None] = Field(default_factory=dict)
    percentiles: dict[str, float | None] = Field(default_factory=dict)
    ranks: dict[str, int | None] = Field(default_factory=dict)
    winners: list[str] = Field(default_factory=list)


class DimensionComparison(BaseModel):
    """A group of aligned metrics for one analytical dimension."""

    name: str
    metrics: list[MetricComparison] = Field(default_factory=list)


class ScorecardRow(BaseModel):
    """One ticker's roll-up across all ranked metrics."""

    ticker: str
    company_name: str = ""
    overall_score: float | None = None   # equal-weighted mean of normalized scores
    wins: int = 0
    metrics_scored: int = 0


class TickerError(BaseModel):
    """A ticker that could not be analyzed and was skipped."""

    ticker: str
    error: str


class ComparativeReport(BaseModel):
    """Full comparative result: the per-ticker report models + comparison layer."""

    requested_tickers: list[str]
    tickers: list[str] = Field(default_factory=list)   # successfully analyzed, in order
    company_names: dict[str, str] = Field(default_factory=dict)
    currencies: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime
    scorecard: list[ScorecardRow] = Field(default_factory=list)
    dimensions: list[DimensionComparison] = Field(default_factory=list)
    errors: list[TickerError] = Field(default_factory=list)
    data_sources: dict[str, list[str]] = Field(default_factory=dict)
    # Issue #74: per-ticker structured source records (name + reference link),
    # so the comparative report enumerates every source instead of bare labels.
    source_records: dict[str, list[SourceRecord]] = Field(default_factory=dict)
    deferred_dimensions: list[str] = Field(default_factory=list)
    per_ticker_reports: list[ResearchResponse] = Field(default_factory=list)
    disclaimer: str = _DISCLAIMER
    compliance_note: str = _COMPLIANCE_NOTE


# ---------------------------------------------------------------------------
# Pure builder: per-ticker responses -> comparison layer
# ---------------------------------------------------------------------------

def _comprehensive_report(resp: ResearchResponse) -> ReportOutput | None:
    """Pick the comprehensive report from a response, falling back to the first."""
    for report in resp.reports:
        if report.report_type == ReportType.COMPREHENSIVE:
            return report
    return resp.reports[0] if resp.reports else None


def build_comparative_report(
    responses: list[ResearchResponse],
    errors: Iterable[TickerError] | None = None,
    requested: Iterable[str] | None = None,
) -> ComparativeReport:
    """Build the comparison layer from per-ticker responses. Pure, no I/O."""
    error_list = list(errors or [])
    tickers = [resp.ticker for resp in responses]
    requested_list = list(requested) if requested is not None else list(tickers)
    company_names = {resp.ticker: resp.company_name for resp in responses}
    currencies = {resp.ticker: getattr(resp, "currency", "USD") for resp in responses}
    data_sources = {resp.ticker: list(resp.metadata.data_sources) for resp in responses}
    # Issue #74: carry each ticker's linked source records into the comparison.
    source_records = {
        resp.ticker: list(resp.metadata.source_records) for resp in responses
    }

    reports_by_ticker: dict[str, ReportOutput] = {}
    for resp in responses:
        rep = _comprehensive_report(resp)
        if rep is not None:
            reports_by_ticker[resp.ticker] = rep

    # Extract + rank every metric.
    metric_objs: dict[str, MetricComparison] = {}
    for spec in METRIC_REGISTRY:
        values: dict[str, float | None] = {}
        for t in tickers:
            rep = reports_by_ticker.get(t)
            raw: float | None = None
            if rep is not None:
                try:
                    raw = spec.extract(rep)
                except Exception:  # defensive: a bad field never breaks the set
                    raw = None
            values[t] = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None

        available = any(v is not None for v in values.values())
        mc = MetricComparison(
            key=spec.key, label=spec.label, dimension=spec.dimension, unit=spec.unit,
            higher_is_better=spec.higher_is_better, rankable=spec.rankable,
            source=spec.source, available=available, values=values,
        )
        if spec.rankable and available:
            ranked = rank_metric(values, spec.higher_is_better)
            mc.normalized = {t: ranked[t].normalized for t in tickers}
            mc.percentiles = {t: ranked[t].percentile for t in tickers}
            mc.ranks = {t: ranked[t].rank for t in tickers}
            mc.winners = [t for t in tickers if ranked[t].is_winner]
        metric_objs[spec.key] = mc

    # Assemble dimensions (only those with at least one available metric).
    dimensions: list[DimensionComparison] = []
    for dim in DIMENSION_ORDER:
        dim_metrics = [
            metric_objs[spec.key]
            for spec in METRIC_REGISTRY
            if spec.dimension == dim and metric_objs[spec.key].available
        ]
        if dim_metrics:
            dimensions.append(DimensionComparison(name=dim, metrics=dim_metrics))

    # Scorecard: equal-weighted mean of normalized rankable metrics per ticker.
    scorecard: list[ScorecardRow] = []
    for t in tickers:
        norms: list[float] = []
        wins = 0
        for mc in metric_objs.values():
            if not (mc.rankable and mc.available):
                continue
            n = mc.normalized.get(t)
            if n is not None:
                norms.append(n)
            if t in mc.winners:
                wins += 1
        overall = round(sum(norms) / len(norms), 1) if norms else None
        scorecard.append(ScorecardRow(
            ticker=t, company_name=company_names.get(t, ""),
            overall_score=overall, wins=wins, metrics_scored=len(norms),
        ))
    scorecard.sort(key=lambda r: (r.overall_score is not None, r.overall_score or 0.0), reverse=True)

    return ComparativeReport(
        requested_tickers=requested_list,
        tickers=tickers,
        company_names=company_names,
        currencies=currencies,
        generated_at=datetime.now(timezone.utc),
        scorecard=scorecard,
        dimensions=dimensions,
        errors=error_list,
        data_sources=data_sources,
        source_records=source_records,
        deferred_dimensions=list(DEFERRED_DIMENSIONS),
        per_ticker_reports=list(responses),
    )


# ---------------------------------------------------------------------------
# Orchestrator: run the existing single-ticker pipeline per ticker
# ---------------------------------------------------------------------------

SingleRunFn = Callable[[ResearchRequest], Awaitable[ResearchResponse]]

_TIMEFRAME_MAP = {
    "1M": Timeframe.ONE_MONTH, "3M": Timeframe.THREE_MONTHS,
    "6M": Timeframe.SIX_MONTHS, "1Y": Timeframe.ONE_YEAR,
    "3Y": Timeframe.THREE_YEARS, "5Y": Timeframe.FIVE_YEARS,
    "10Y": Timeframe.TEN_YEARS,
}


class ComparativeOrchestrator:
    """Runs the existing single-ticker orchestrator once per ticker, then ranks.

    Reuses the whole per-ticker pipeline (which itself already runs
    ``competitor.py`` for peer-relative context) — this layer adds only the
    cross-ticker alignment and ranking. An invalid ticker is skipped and
    recorded; it never crashes the request.
    """

    def __init__(
        self,
        orchestrator: ResearchOrchestrator | None = None,
        runner: SingleRunFn | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        if runner is not None:
            self._run_single: SingleRunFn = runner
        else:
            if orchestrator is None:
                # Lazy import: keeps the pure comparison layer (models, ranking,
                # renderer) importable without pulling the heavy provider tree.
                from .orchestrator import ResearchOrchestrator
                orchestrator = ResearchOrchestrator()
            self._orchestrator = orchestrator
            self._run_single = self._orchestrator.run
        self._concurrency = max(1, concurrency)

    @staticmethod
    def normalize_tickers(tickers: Iterable[str]) -> list[str]:
        """Upper-case, strip, and de-duplicate while preserving order."""
        seen: set[str] = set()
        out: list[str] = []
        for t in tickers:
            if not isinstance(t, str):
                continue
            u = t.strip().upper()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    async def run(self, tickers: Iterable[str], timeframe: str = "1Y") -> ComparativeReport:
        """Run the comparison. Raises ValueError only for an invalid ticker count."""
        norm = self.normalize_tickers(tickers)
        if not (MIN_TICKERS <= len(norm) <= MAX_TICKERS):
            raise ValueError(
                f"Comparative reports require between {MIN_TICKERS} and {MAX_TICKERS} "
                f"distinct tickers; got {len(norm)}."
            )

        tf = _TIMEFRAME_MAP.get(timeframe.upper(), Timeframe.ONE_YEAR)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _one(tk: str) -> ResearchResponse:
            async with semaphore:
                req = ResearchRequest(
                    ticker=tk,
                    report_types=[ReportType.COMPREHENSIVE],
                    timeframe=tf,
                )
                return await self._run_single(req)

        results = await asyncio.gather(*[_one(t) for t in norm], return_exceptions=True)

        responses: list[ResearchResponse] = []
        errors: list[TickerError] = []
        for tk, res in zip(norm, results):
            if isinstance(res, BaseException):
                logger.warning("Comparative: skipping %s (%s): %s", tk, type(res).__name__, res)
                errors.append(TickerError(ticker=tk, error=f"{type(res).__name__}: {res}"))
            else:
                responses.append(res)

        return build_comparative_report(responses, errors=errors, requested=norm)
