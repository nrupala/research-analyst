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

"""Pydantic data models — the single source of truth for all data structures.

Every piece of data that flows through the system has a typed model here.
No dicts, no untyped containers, no guessing.
"""
# Module: research_analyst/models.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .disclaimer import DISCLAIMER_SHORT
from .enums import (
    ReportType,
    RiskCategory,
    RiskDuration,
    RiskNature,
    ScenarioType,
    SecurityType,
    Timeframe,
)

# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    """Inbound research request from user or API."""

    # 20 chars, matching the API layer and the market-data provider:
    # suffixed international tickers (RELIANCE.NS = 11, TATAMOTORS.NS
    # = 13) must fit. The three layers drifted at 10/20/10 and the
    # tightest silently rejected India — aligned 2026-10-15.
    ticker: str = Field(..., min_length=1, max_length=20, description="Equity or ETF ticker symbol")
    report_types: list[ReportType] = Field(
        default_factory=lambda: [ReportType.COMPREHENSIVE],
        description="Which report(s) to generate. Default: comprehensive.",
    )
    compare_tickers: list[str] = Field(
        default_factory=list,
        description="Additional tickers for comparative analysis.",
    )
    timeframe: Timeframe = Field(default=Timeframe.ONE_YEAR)
    custom_assumptions: dict[str, Any] = Field(
        default_factory=dict,
        description="User-provided assumption overrides (growth rates, margins, etc.).",
    )

    @field_validator("ticker", "compare_tickers", mode="before")
    @classmethod
    def _uppercase_tickers(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        if isinstance(v, list):
            return [t.strip().upper() for t in v if t.strip()]
        return v


class ResearchResponse(BaseModel):
    """Outbound research result."""

    ticker: str
    security_type: SecurityType
    company_name: str
    currency: str = "USD"
    generated_at: datetime
    reports: list[ReportOutput]
    metadata: ResearchMetadata


class ResearchMetadata(BaseModel):
    """Provenance and transparency metadata."""

    data_sources: list[str] = Field(default_factory=list)
    data_freshness: dict[str, str] = Field(default_factory=dict)
    assumptions_used: list[Assumption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_time_seconds: float = 0.0
    # --- Evidence integrity (#66-#74) ----------------------------------
    data_as_of: str | None = None  # #66: e.g. "2026-09-24 (previous close)"
    quotes_disclosure: str = (  # #66
        "Quotes are delayed to the previous trading day's close (end-of-day data)."
    )
    sla_state: str = "fresh"  # #66: "fresh" | "stale" | "degraded"
    cache_hit: bool = False  # #66
    cached_at_utc: datetime | None = None  # #66
    stale_warning: str | None = None  # #66: rendered prominently when set
    source_records: list[SourceRecord] = Field(default_factory=list)  # #74
    peer_set: PeerSetProvenance | None = None  # #67
    input_snapshot: InputSnapshot | None = None  # #69


# ---------------------------------------------------------------------------
# Company / Security Profile
# ---------------------------------------------------------------------------


class CompanyProfile(BaseModel):
    """Core company or ETF profile data."""

    ticker: str
    name: str
    security_type: SecurityType
    sector: str = ""
    industry: str = ""
    sub_industry: str = ""
    market_cap: Decimal | None = None
    enterprise_value: Decimal | None = None
    employees: int | None = None
    country: str = ""
    exchange: str = ""
    currency: str = "USD"
    description: str = ""
    website: str = ""
    cik: str = ""  # SEC Central Index Key
    fiscal_year_end: str = ""  # e.g., "December"


class PriceData(BaseModel):
    """OHLCV price data for a single period."""

    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int


class PriceSeries(BaseModel):
    """Time series of price data with computed fields."""

    ticker: str
    data: list[PriceData]
    period_start: date
    period_end: date
    # Price fields are None when the source returned no data — missing
    # stays missing, never a fabricated 0.0 (owner doctrine; a report
    # rendered "Current Price: $0.00" for META on 2026-10-15 when Stooq
    # returned an empty frame). Consumers must handle None explicitly.
    current_price: float | None = None
    price_52w_high: float | None = None
    price_52w_low: float | None = None
    avg_volume_30d: float = 0.0
    avg_volume_90d: float = 0.0
    ytd_return: float | None = None
    total_return_1y: float | None = None
    # Which cascade step served these prices: "nasdaq", "tiingo",
    # "alphavantage", "stooq", or "yfinance" (owner cascade,
    # 2026-10-15). "" when no
    # source served or for legacy cache entries. The orchestrator
    # declares it in the report's Data Sources list, and renderers
    # show it in small print next to the price (price_source_label).
    data_source: str = ""


# Display names for the price cascade's steps, keyed by
# PriceSeries.data_source (owner cascade directive, 2026-10-15: the
# source in play is indicated next to the price).
PRICE_SOURCE_LABELS: dict[str, str] = {
    "nasdaq": "Nasdaq",
    "tiingo": "Tiingo",
    "alphavantage": "Alpha Vantage",
    "twelvedata": "Twelve Data",
    "fmp": "FMP",
    "stooq": "Stooq",
    "yfinance": "Yahoo Finance",
}


def price_source_label(data_source: str) -> str:
    """Small-print source note for a price, e.g. ' (source: Nasdaq)'.

    Empty when the serving source is unknown (no source served, or a
    legacy cache entry) — an unlabeled price is never dressed up with
    a guessed source.
    """
    name = PRICE_SOURCE_LABELS.get(data_source)
    return f" (source: {name})" if name else ""


# ---------------------------------------------------------------------------
# Fundamental Data
# ---------------------------------------------------------------------------


class FinancialStatement(BaseModel):
    """Standardized financial statement line items."""

    period: str  # e.g., "FY2025", "Q1 2026"
    period_end_date: date | None = None
    is_annual: bool = True

    # Income Statement
    revenue: Decimal | None = None
    cost_of_revenue: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_income: Decimal | None = None
    ebitda: Decimal | None = None
    ebit: Decimal | None = None
    net_income: Decimal | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    shares_outstanding: int | None = None
    shares_diluted: int | None = None
    interest_expense: Decimal | None = None
    tax_expense: Decimal | None = None
    sga_expense: Decimal | None = None
    depreciation_amortization: Decimal | None = None

    # Margins (computed)
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    ebitda_margin: float | None = None

    # Balance Sheet
    total_assets: Decimal | None = None
    total_liabilities: Decimal | None = None
    total_equity: Decimal | None = None
    cash_and_equivalents: Decimal | None = None
    total_debt: Decimal | None = None
    net_debt: Decimal | None = None
    current_assets: Decimal | None = None
    current_liabilities: Decimal | None = None
    retained_earnings: Decimal | None = None
    ppe_net: Decimal | None = None
    receivables: Decimal | None = None

    # Cash Flow
    operating_cash_flow: Decimal | None = None
    capex: Decimal | None = None
    free_cash_flow: Decimal | None = None
    dividends_paid: Decimal | None = None
    share_buybacks: Decimal | None = None

    # Ratios
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    interest_coverage: float | None = None


class FundamentalData(BaseModel):
    """Aggregated fundamental data for a security."""

    profile: CompanyProfile
    financials: list[FinancialStatement] = Field(default_factory=list)
    analyst_estimates: AnalystEstimates | None = None
    insider_activity: list[InsiderTransaction] = Field(default_factory=list)
    institutional_holders: list[InstitutionalHolder] = Field(default_factory=list)


class AnalystEstimates(BaseModel):
    """Consensus analyst estimates."""

    target_price_mean: float | None = None
    target_price_median: float | None = None
    target_price_high: float | None = None
    target_price_low: float | None = None
    num_analysts: int = 0
    recommendation_mean: float | None = None  # 1=Strong Buy, 5=Sell
    eps_estimate_current_year: float | None = None
    eps_estimate_next_year: float | None = None
    revenue_estimate_current_year: Decimal | None = None
    revenue_estimate_next_year: Decimal | None = None
    earnings_growth_5y: float | None = None


class InsiderTransaction(BaseModel):
    """SEC Form 4 insider transaction."""

    filer_name: str
    filer_title: str = ""
    transaction_date: date
    transaction_type: str  # "Purchase", "Sale", "Option Exercise"
    shares: int
    price_per_share: float | None = None
    total_value: Decimal | None = None
    shares_owned_after: int | None = None


class InstitutionalHolder(BaseModel):
    """Institutional ownership data."""

    holder_name: str
    shares: int
    value: Decimal | None = None
    pct_held: float | None = None
    date_reported: date | None = None
    change_pct: float | None = None  # Quarter-over-quarter change


# ---------------------------------------------------------------------------
# Technical Analysis
# ---------------------------------------------------------------------------


class TechnicalIndicators(BaseModel):
    """Computed technical indicators at a point in time."""

    ticker: str
    as_of_date: date

    # Moving Averages
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None

    # Trend
    price_vs_sma_200: str = ""  # "above" / "below"
    sma_50_vs_200: str = ""  # "golden_cross" / "death_cross" / "neutral"

    # Momentum
    rsi_14: float | None = None
    rsi_signal: str = ""  # "overbought" / "oversold" / "neutral"
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    macd_crossover: str = ""  # "bullish" / "bearish" / "none"

    # Volatility
    bollinger_upper: float | None = None
    bollinger_middle: float | None = None
    bollinger_lower: float | None = None
    bollinger_position: str = ""  # "above_upper" / "below_lower" / "within"
    atr_14: float | None = None
    atr_pct: float | None = None  # ATR as % of price

    # Volume
    volume_trend: str = ""  # "increasing" / "decreasing" / "stable"
    obv_trend: str = ""  # "accumulation" / "distribution" / "neutral"
    adx_14: float | None = None
    adx_signal: str = ""  # "strong_trend" / "weak_trend" / "no_trend"

    # Support / Resistance
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)

    # Patterns
    patterns_detected: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Macro Context
# ---------------------------------------------------------------------------


class MacroSnapshot(BaseModel):
    """Point-in-time macro environment data."""

    as_of_date: date

    # Rates
    fed_funds_rate: float | None = None
    us_10y_yield: float | None = None
    us_2y_yield: float | None = None
    yield_curve_spread: float | None = None  # 10Y - 2Y
    yield_curve_signal: str = ""  # "normal" / "inverted" / "flat"

    # Inflation
    cpi_yoy: float | None = None
    core_cpi_yoy: float | None = None
    pce_yoy: float | None = None
    breakeven_inflation_5y: float | None = None

    # Growth
    gdp_growth_latest: float | None = None
    gdp_growth_forecast: float | None = None
    unemployment_rate: float | None = None
    ism_manufacturing: float | None = None
    ism_services: float | None = None

    # Market
    vix: float | None = None
    sp500_pe: float | None = None
    credit_spread_ig: float | None = None
    credit_spread_hy: float | None = None
    dxy_index: float | None = None  # Dollar index

    # First-source supplements (source registry step 1, 2026-10-14).
    # Official rates wired as provenance-carrying extras: no engine
    # consumes them yet and they never overwrite the fields above.
    # Rates are stored as fractions, matching the fields above.
    treasury_avg_rates: dict[str, float] = Field(default_factory=dict)
    treasury_as_of: date | None = None
    boc_policy_rate: float | None = None  # fraction
    boc_usd_cad: float | None = None  # CAD per USD, as published
    boc_as_of: date | None = None

    # First-source supplements (source registry step 2, 2026-10-14).
    # Same provenance-only rule as step 1: no engine consumes these yet
    # and they never overwrite the fields above. Rates/HICP/GDP are
    # stored as fractions; FX exactly as published.
    ecb_eur_usd: float | None = None  # USD per EUR (ECB reference rate)
    ecb_eur_usd_as_of: date | None = None
    ecb_deposit_facility_rate: float | None = None  # fraction
    ecb_deposit_facility_as_of: date | None = None
    ecb_hicp_yoy: float | None = None  # fraction, euro area
    ecb_hicp_as_of: date | None = None
    bundesbank_bund_10y_yield: float | None = None  # fraction, monthly
    bundesbank_bund_10y_as_of: date | None = None
    eurostat_hicp_yoy: float | None = None  # fraction, EU27
    eurostat_hicp_as_of: date | None = None
    eurostat_gdp_growth: float | None = None  # fraction, EA21 annual
    eurostat_gdp_as_of: date | None = None
    boj_usd_jpy: float | None = None  # JPY per USD, as published
    boj_usd_jpy_as_of: date | None = None
    boj_policy_rate: float | None = None  # fraction (basic discount/loan rate)
    boj_policy_rate_as_of: date | None = None
    supplemental_sources: list[str] = Field(default_factory=list)

    # Cycle
    cycle_phase: str = ""  # "expansion" / "peak" / "contraction" / "trough"
    cycle_confidence: float | None = None


# ---------------------------------------------------------------------------
# Competitor Analysis
# ---------------------------------------------------------------------------


class Competitor(BaseModel):
    """Discovered competitor profile."""

    ticker: str
    name: str
    market_cap: Decimal | None = None
    revenue: Decimal | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    pe_ratio: float | None = None
    ev_ebitda: float | None = None
    revenue_growth_yoy: float | None = None
    roe: float | None = None
    roic: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow_yield: float | None = None
    dividend_yield: float | None = None  # trailing, fraction (v0.1.1)


class CompetitiveLandscape(BaseModel):
    """Full competitive context."""

    target: Competitor
    peers: list[Competitor] = Field(default_factory=list)
    sector: str = ""
    industry: str = ""
    target_rank_by_market_cap: int | None = None
    target_rank_by_revenue: int | None = None
    competitive_advantages: list[str] = Field(default_factory=list)
    competitive_risks: list[str] = Field(default_factory=list)
    peer_set_note: str = ""  # #67: versioned peer-universe coverage note


# ---------------------------------------------------------------------------
# Risk Framework
# ---------------------------------------------------------------------------


class StructuredRisk(BaseModel):
    """Single risk — structured by Probability x Impact x Timing."""

    title: str
    description: str
    category: RiskCategory
    probability: str  # "Low (<20%)" / "Medium (20-50%)" / "High (>50%)"
    probability_pct: float | None = None  # Quantified where possible
    impact: str  # "Low" / "Medium" / "High" / "Critical"
    impact_description: str = ""
    timing: RiskDuration
    nature: RiskNature
    mitigants: list[str] = Field(default_factory=list)
    monitoring_triggers: list[str] = Field(default_factory=list)
    second_order_effects: list[str] = Field(default_factory=list)


class RiskMatrix(BaseModel):
    """Complete risk assessment for a security."""

    ticker: str
    risks: list[StructuredRisk] = Field(default_factory=list)
    overall_risk_score: float | None = None  # 1-10 composite
    key_risk_summary: str = ""
    # --- Score derivation (#71): every published score shows its math ----
    score_breakdown: list[RiskScoreComponent] = Field(default_factory=list)
    score_formula: str = (
        "overall = round(sum(probability_score x impact_score for each risk) "
        "/ (12 x number of risks) x 10, 1); probability Low(<20%)=1 / Medium(20-50%)=2 / "
        "High(>50%)=3; impact Low=1 / Medium=2 / High=3 / Critical=4; "
        "severity 8-12 = critical"
    )
    score_baseline_note: str = ""  # set when the score is a default, not computed


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------


class Assumption(BaseModel):
    """Explicit, traceable assumption — mandatory for every conclusion."""

    label: str
    value: str
    source: str = ""  # Where this comes from
    confidence: str = ""  # "High" / "Medium" / "Low"
    note: str = ""


# ---------------------------------------------------------------------------
# Evidence integrity (#66-#74)
# ---------------------------------------------------------------------------


class SourceRecord(BaseModel):
    """One enumerated, referenceable data source (#74).

    ``name`` keeps the legacy human-readable label (e.g. "yfinance (price
    data)"). ``url`` is a best-effort reference link — never a bare count.
    """

    name: str
    url: str | None = None
    accessed_at_utc: datetime | None = None


class PeerSetProvenance(BaseModel):
    """Deterministic peer-universe provenance (#67)."""

    map_version: str = ""  # e.g. "2026.09"
    map_hash: str = ""  # sha256 of the canonical peer-map JSON (first 16 hex)
    expected_tickers: list[str] = Field(default_factory=list)
    resolved_tickers: list[str] = Field(default_factory=list)
    missing_tickers: list[str] = Field(default_factory=list)

    @property
    def coverage_note(self) -> str:
        n, m = len(self.resolved_tickers), len(self.expected_tickers)
        note = (
            f"Peer universe v{self.map_version} (map hash {self.map_hash}): "
            f"{n} of {m} expected peers resolved."
        )
        if self.missing_tickers:
            note += (
                " Missing expected peers (data unavailable, excluded — not silently dropped): "
                + ", ".join(self.missing_tickers)
            )
        return note


class InputSnapshot(BaseModel):
    """Immutable snapshot of the fundamental inputs one report was built from (#69).

    Every number in the report traces to this single input set. The hash is
    over the canonical JSON of ``inputs`` so reproducibility is checkable.
    """

    captured_at_utc: datetime
    input_hash: str = ""  # sha256 hex of canonical inputs JSON
    inputs: dict[str, Any] = Field(default_factory=dict)


class RiskScoreComponent(BaseModel):
    """One risk's contribution to the composite risk score (#71)."""

    title: str
    probability_score: int  # 1-4 mapped from probability class
    impact_score: int  # 1-3 mapped from impact class
    severity: int  # probability_score * impact_score (1-12)
    weight_share: float = 0.0  # severity / total severity, fraction


class ValuationScenario(BaseModel):
    """Single scenario within the valuation range."""

    scenario_type: ScenarioType
    label: str  # e.g., "Bull Case"
    assumptions: list[Assumption]
    revenue_growth: float | None = None
    operating_margin: float | None = None
    pe_multiple: float | None = None
    ev_ebitda_multiple: float | None = None
    fcf_yield: float | None = None
    discount_rate: float | None = None
    terminal_growth: float | None = None
    implied_price_low: float | None = None
    implied_price_high: float | None = None
    implied_upside_low: float | None = None  # % from current
    implied_upside_high: float | None = None
    narrative: str = ""


class ValuationRange(BaseModel):
    """Scenario-based valuation — mandatory in every report."""

    ticker: str
    current_price: float | None = None  # None = price unavailable from the source
    scenarios: list[ValuationScenario] = Field(default_factory=list)
    primary_methodology: str = ""  # "DCF" / "Relative" / "Sum-of-Parts" / "Hybrid"
    variant_perception: VariantPerception | None = None

    def ascii_chart(self) -> str:
        """Generate mandatory ASCII scenario summary."""
        lines: list[str] = []
        if not self.scenarios:
            return ""
        max_price = max((s.implied_price_high or 0) for s in self.scenarios) or 1.0
        for s in self.scenarios:
            if s.implied_price_low is not None and s.implied_price_high is not None:
                bar_len = int((s.implied_price_high / max_price) * 20)
                bar = "\u2588" * max(bar_len, 1)
                lines.append(
                    f"    {s.label:<12} {bar:<20}  "
                    f"${s.implied_price_low:.0f}\u2013${s.implied_price_high:.0f}"
                )
        return "\n".join(lines)


class VariantPerception(BaseModel):
    """Consensus vs differentiated view — mandatory per spec."""

    consensus_view: str
    variant_view: str
    why_it_matters: str


# ---------------------------------------------------------------------------
# Capital Allocation
# ---------------------------------------------------------------------------


class CapitalAllocation(BaseModel):
    """Capital allocation analysis — capex vs buybacks vs M&A vs dividends."""

    ticker: str
    period: str  # "FY2025" or "TTM"

    # Allocation breakdown
    capex: Decimal | None = None
    capex_pct_of_fcf: float | None = None
    rd_spend: Decimal | None = None
    rd_pct_of_revenue: float | None = None
    share_buybacks: Decimal | None = None
    buyback_pct_of_fcf: float | None = None
    dividends: Decimal | None = None
    dividend_pct_of_fcf: float | None = None
    ma_spend: Decimal | None = None
    debt_repayment: Decimal | None = None

    # Return analysis
    roic: float | None = None
    wacc: float | None = None
    roic_minus_wacc: float | None = None
    marginal_roic_trend: str = ""  # "improving" / "declining" / "stable"
    reinvestment_rate: float | None = None
    shareholder_yield: float | None = None  # buyback + dividend yield

    assessment: str = ""  # Free-text assessment of capital allocation quality


# ---------------------------------------------------------------------------
# Dividend & Yield (v0.1.1)
# ---------------------------------------------------------------------------


class DividendPayment(BaseModel):
    """A single dividend distribution (per-share, in the security's currency)."""

    ex_date: date
    amount: float


class DividendData(BaseModel):
    """Raw dividend / yield data from the market-data provider.

    The headline yield is computed downstream from dividend_rate / current_price;
    the info_* fields are cross-checks only, because yfinance has historically
    shipped ``dividendYield`` as both a fraction (0.025) and a percent (2.5).
    """

    ticker: str
    currency: str = "USD"
    is_etf: bool = False
    current_price: float | None = None

    # Annualized per-share rates ($/share)
    dividend_rate: float | None = None  # forward annual
    trailing_dividend_rate: float | None = None  # trailing 12 months

    # yfinance .info yield fields (raw, un-normalized) — cross-checks only
    info_dividend_yield: float | None = None
    info_payout_ratio: float | None = None
    five_year_avg_yield: float | None = None  # yfinance reports this as a percent
    etf_ttm_yield: float | None = None  # ETF distribution yield (fraction)

    # Most recent payment metadata
    ex_dividend_date: date | None = None
    last_dividend_value: float | None = None
    last_dividend_date: date | None = None

    # Full per-share history (chronological)
    history: list[DividendPayment] = Field(default_factory=list)


class DividendAnalysis(BaseModel):
    """Structured dividend & yield assessment (v0.1.1).

    Every figure is computed and carries an explicit assumption. Non-payers get
    ``pays_dividend=False`` with ``no_dividend_context`` explaining the policy.
    All yields are stored as fractions (0.025 == 2.5%).
    """

    ticker: str
    pays_dividend: bool = False
    is_etf: bool = False
    income_label: str = "Dividend"  # "Dividend" or "Distribution" (ETF)

    # Yield
    current_yield: float | None = None  # forward, fraction
    trailing_yield: float | None = None  # trailing 12m, fraction
    five_year_avg_yield: float | None = None  # fraction
    annual_dividend_rate: float | None = None  # forward $/share
    ex_dividend_date: date | None = None

    # Growth
    dividend_growth_1y: float | None = None
    dividend_growth_3y_cagr: float | None = None
    dividend_growth_5y_cagr: float | None = None

    # Payout / coverage (trailing basis)
    payout_ratio_eps: float | None = None  # dividends paid / net income
    payout_ratio_fcf: float | None = None  # dividends paid / free cash flow
    eps_coverage: float | None = None  # net income / dividends paid
    fcf_coverage: float | None = None  # free cash flow / dividends paid

    # Consistency
    consecutive_increase_years: int = 0
    had_cut: bool = False
    years_since_cut: int | None = None
    paying_years: int = 0

    # Safety
    safety_score: float | None = None  # 0-100
    safety_grade: str = ""  # Very Safe / Safe / Borderline / At Risk / Unsafe

    # Yield context
    us_10y_yield: float | None = None
    yield_vs_treasury_spread: float | None = None  # current_yield - 10Y
    peer_median_yield: float | None = None
    yield_vs_peers: str = ""  # "above" / "below" / "in line"
    attractiveness_rating: str = ""  # Attractive / Fairly Valued / Unattractive / Yield-Trap Risk
    attractiveness_rationale: str = ""

    # Non-payers
    no_dividend_context: str = ""

    # Chart support — calendar-year DPS totals (year -> sum of per-share dividends)
    annual_dividends: dict[str, float] = Field(default_factory=dict)

    # Traceability
    assumptions: list[Assumption] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Report Output
# ---------------------------------------------------------------------------


class ReportSection(BaseModel):
    """Single section within a 7-step report."""

    step_number: int
    title: str
    content: str  # Markdown
    visuals: list[ReportVisual] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class ReportVisual(BaseModel):
    """Visual element within a report."""

    visual_type: str  # "svg" / "ascii" / "table"
    title: str
    content: str  # Code or markup
    ties_to: str = ""  # Which assumption / scenario / risk this supports
    caption: str = ""
    interactive: dict[str, Any] | None = None  # trace-ready data for the on-demand interactive view


class ReportOutput(BaseModel):
    """Complete generated report."""

    report_type: ReportType
    ticker: str
    title: str
    generated_at: datetime
    sections: list[ReportSection]
    valuation: ValuationRange | None = None
    risk_matrix: RiskMatrix | None = None
    capital_allocation: CapitalAllocation | None = None
    dividend: DividendAnalysis | None = None
    security_type: SecurityType | None = None  # set by the renderer (ETF topic mapping)
    disclaimer: str = ""  # Set by __init__ to DISCLAIMER_SHORT from disclaimer.py
    lenses: list[Any] = Field(default_factory=list)  # typed LensResults (Phase 5)

    def to_markdown(self, metadata: ResearchMetadata | None = None) -> str:
        """Render full report as Markdown.

        ``metadata`` (the run's ResearchMetadata) unlocks the provenance
        footer: data-freshness block (#66), enumerated sources (#74) and the
        input-snapshot appendix (#69). Callers without metadata get the same
        body as before.
        """
        parts: list[str] = [f"# {self.title}\n"]
        parts.append(f"**Ticker:** {self.ticker} | **Report Type:** {self.report_type.value}")
        parts.append(f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        if metadata is not None:
            parts.append(self._freshness_header(metadata))
        parts.append("---\n")

        for section in self.sections:
            # Sections with step_number=0 are post-template appendices
            # (e.g. the Quantitative Engine section) — never a fake "Step 8".
            if section.step_number > 0:
                parts.append(f"## Step {section.step_number}: {section.title}\n")
            else:
                parts.append(f"## {section.title}\n")
            parts.append(section.content)

            for visual in section.visuals:
                parts.append(f"\n### {visual.title}")
                if visual.visual_type == "svg":
                    parts.append('<div class="chart-svg">')
                    parts.append(visual.content)
                    parts.append("</div>")
                    if visual.interactive:
                        import base64 as _b64
                        import json as _json

                        _enc = _b64.b64encode(_json.dumps(visual.interactive).encode()).decode()
                        parts.append(
                            '<button type="button" class="chart-interactive" '
                            f'data-interactive="{_enc}">'
                            "Interactive view \u2197</button>"
                        )
                elif visual.visual_type == "table":
                    parts.append(visual.content)
                else:
                    parts.append(f"```\n{visual.content}\n```")
                if visual.caption:
                    parts.append(f"*{visual.caption}*")

            if section.assumptions:
                parts.append("\n**Assumptions Used:**")
                for a in section.assumptions:
                    src = f" (Source: {a.source})" if a.source else ""
                    parts.append(f"- **{a.label}:** {a.value}{src}")

            if section.data_gaps:
                parts.append("\n**Data Gaps:**")
                for gap in section.data_gaps:
                    parts.append(f"- {gap}")

            parts.append("")

        # Valuation ASCII chart — mandatory
        if self.valuation:
            parts.append("## Scenario-Based Valuation Range\n")
            if self.valuation.current_price is not None:
                parts.append(f"**Current Price:** ${self.valuation.current_price:.2f}\n")
            else:
                parts.append("**Current Price:** Not available (no price data from the source)\n")
            parts.append(f"```\n{self.valuation.ascii_chart()}\n```\n")

            # #72: the step sections already develop the variant perception
            # in full; rendering it again here duplicated the whole block
            # verbatim in every comprehensive report. Only render it in
            # this appendix when no section carried it.
            if self.valuation.variant_perception and not any(
                "Variant Perception" in (s.content or "") for s in self.sections
            ):
                vp = self.valuation.variant_perception
                parts.append("### Variant Perception\n")
                parts.append(f"- **Consensus View:** {vp.consensus_view}")
                parts.append(f"- **Variant View:** {vp.variant_view}")
                parts.append(f"- **Why It Matters:** {vp.why_it_matters}")

        # Mental-model lenses (Phase 5) — educational, attribution-safe
        if self.lenses:
            parts.append("## Mental-Model Lenses (Educational Frameworks)\n")
            parts.append(
                "The following lenses apply public-domain evaluation methodologies "
                "to the report's data. They are educational models, not verdicts.\n"
            )
            # #70: the synthesis is computed from the lens outputs below —
            # never a static template — so it differs ticker to ticker.
            parts.extend(self._lens_synthesis())
            for lens in self.lenses:
                parts.append(f"### {lens.name}\n")
                parts.append(lens.summary)
                parts.append("")
                for sig in lens.signals:
                    read_icon = {
                        "favor": "▲ Favor",
                        "caution": "▼ Caution",
                        "neutral": "• Neutral",
                    }.get(sig.read, "• Neutral")
                    parts.append(f"- **{sig.label}:** {sig.value} — {read_icon}")
                    if sig.note:
                        parts.append(f"  {sig.note}")
                parts.append("")
                # #70: show the lens's inputs and raw calculation so the
                # result is verifiable, not decorative.
                raw = getattr(lens, "raw_values", None) or {}
                missing = getattr(lens, "missing_inputs", None) or []
                if raw or missing:
                    parts.append("<details><summary><b>Inputs & calculation</b></summary>\n")
                    for key, value in raw.items():
                        parts.append(f"- `{key}`: {self._fmt_raw_value(value)}")
                    if missing:
                        parts.append(
                            "- **Missing inputs (named explicitly):** "
                            + ", ".join(f"`{m}`" for m in missing)
                        )
                    parts.append("</details>\n")
                if lens.attribution:
                    parts.append(f"*{lens.attribution}*\n")

        # thinkwithfinance cross-reference (Phase 4) — empty until content ships
        from .crossref import render_crossref_block

        parts.append(
            render_crossref_block(
                self.ticker,
                self.ticker,
                report_type=self.report_type.value,
                is_etf=self.security_type is not None and self.security_type == SecurityType.ETF,
            )
        )

        if metadata is not None:
            parts.append(self._provenance_footer(metadata))

        parts.append("---\n")
        parts.append(f"**Disclaimer:**\n{self.disclaimer or DISCLAIMER_SHORT}")
        return "\n".join(parts)

    # --- Evidence-integrity rendering (#66/#69/#70/#74) --------------------

    def _lens_synthesis(self) -> list[str]:
        """Computed cross-lens synthesis (#70).

        Everything rendered here is derived from the lens results
        themselves — signal reads, margins of safety, cycle position,
        missing inputs — so two tickers with different numbers produce
        visibly different syntheses. Explanations of what each framework
        *is* stay in the per-lens education lines, labelled as education
        in the section intro; this block carries findings only.
        """
        lenses = self.lenses or []
        if not lenses:
            return []
        counts = {"favor": 0, "caution": 0, "neutral": 0}
        for lens in lenses:
            for sig in lens.signals:
                if sig.read in counts:
                    counts[sig.read] += 1
        total = sum(counts.values())
        parts = ["### Lens Synthesis\n"]
        parts.append(
            f"Across {len(lenses)} lenses ({total} signals): "
            f"**{counts['favor']} favor, {counts['caution']} caution, "
            f"{counts['neutral']} neutral.**\n"
        )
        # Intrinsic-value anchors. Both engines report margin of safety as
        # (value - price) / value, so the figures are directly comparable.
        anchors: list[tuple[str, float]] = []
        for lens in lenses:
            raw = getattr(lens, "raw_values", None) or {}
            mos = None
            if lens.lens == "graham":
                mos = raw.get("graham_margin_of_safety")
            elif lens.lens == "damodaran":
                mos = raw.get("margin_of_safety")
            if isinstance(mos, (int, float)):
                anchors.append((lens.name.split("—")[0].strip(), float(mos)))
        if anchors:
            rendered = ", ".join(f"{name} {mos:+.0%}" for name, mos in anchors)
            if all(mos < 0 for _, mos in anchors):
                verdict = (
                    "every computable intrinsic-value anchor sits below the "
                    "current price — the value lenses counsel caution at this price"
                )
            elif all(mos > 0 for _, mos in anchors):
                verdict = (
                    "every computable intrinsic-value anchor sits above the "
                    "current price — the value lenses see a margin of safety"
                )
            else:
                verdict = "the intrinsic-value anchors disagree — the value lenses split"
            parts.append(f"- **Valuation anchors (margin of safety):** {rendered} — {verdict}.")
        # Cycle position (Marks), when that lens computed one.
        for lens in lenses:
            if lens.lens != "marks":
                continue
            raw = getattr(lens, "raw_values", None) or {}
            cyc = raw.get("cycle_position")
            if isinstance(cyc, (int, float)):
                band = "top" if cyc >= 0.8 else ("middle" if cyc >= 0.4 else "bottom")
                parts.append(
                    f"- **Cycle position (Marks):** the multiple sits at {cyc:.0%} "
                    f"of its long-run band ({band} of the range)."
                )
        # Decisive signal per lens: first caution, else first favor.
        for lens in lenses:
            decisive = next((s for s in lens.signals if s.read == "caution"), None) or next(
                (s for s in lens.signals if s.read == "favor"), None
            )
            short = lens.name.split("—")[0].strip()
            if decisive is not None:
                icon = "▼ caution" if decisive.read == "caution" else "▲ favor"
                parts.append(f"- **{short}:** {decisive.label} — {decisive.value} ({icon}).")
            else:
                parts.append(
                    f"- **{short}:** no decisive signal — all reads neutral or data-limited."
                )
        gapped = [lens for lens in lenses if getattr(lens, "missing_inputs", None)]
        if gapped:
            named = "; ".join(
                f"{lens.name.split('—')[0].strip()} ({', '.join(lens.missing_inputs)})"
                for lens in gapped
            )
            parts.append(
                f"- **Data gaps:** {named} — those lenses are partial, "
                "and their reads carry less weight."
            )
        parts.append("")
        return parts

    @staticmethod
    def _fmt_raw_value(value: Any) -> str:
        """Human-readable rendering of a lens raw input/calculation value."""
        if value is None:
            return "n/a (input missing)"
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, float):
            if abs(value) < 10 and value != 0:
                return f"{value:.4f}"
            return f"{value:,.2f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    @staticmethod
    def _freshness_header(metadata: ResearchMetadata) -> str:
        """Reader-visible freshness contract (#66)."""
        lines = ["\n**Data Freshness**"]
        if metadata.data_as_of:
            lines.append(f"- Data as of: **{metadata.data_as_of}**")
        lines.append(f"- {metadata.quotes_disclosure}")
        if metadata.cache_hit:
            cached = (
                metadata.cached_at_utc.strftime("%Y-%m-%d %H:%M UTC")
                if metadata.cached_at_utc
                else "unknown time"
            )
            lines.append(f"- Served from cache (cached at {cached}).")
        sla = metadata.sla_state
        lines.append(f"- Freshness state: **{sla}**")
        if metadata.sla_state == "stale" or metadata.stale_warning:
            lines.append(
                "- ⚠️ **STALE DATA WARNING:** "
                f"{metadata.stale_warning or 'data may be out of date.'}"
            )
        return "\n".join(lines)

    @staticmethod
    def _provenance_footer(metadata: ResearchMetadata) -> str:
        """Sources (#74) and input-snapshot (#69) appendix."""
        parts: list[str] = ["\n## Data Sources\n"]
        records = metadata.source_records or [SourceRecord(name=s) for s in metadata.data_sources]
        if records:
            parts.append("Every figure in this report traces to one of the following sources:\n")
            for i, rec in enumerate(records, 1):
                if rec.url:
                    parts.append(f"{i}. [{rec.name}]({rec.url})")
                else:
                    parts.append(f"{i}. {rec.name}")
        else:
            parts.append("*No data sources recorded.*")
        parts.append("")

        snap = metadata.input_snapshot
        if snap:
            parts.append("## Input Snapshot & Traceability\n")
            parts.append(
                "All numbers in this report were computed from a single snapshotted "
                "input set taken at report time. Any figure can be traced back to "
                "these inputs:\n"
            )
            parts.append(
                f"- Snapshot taken (UTC): {snap.captured_at_utc.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            parts.append(f"- Input hash: `{snap.input_hash}`")
            for key, value in snap.inputs.items():
                parts.append(f"- **{key}:** {value}")
            parts.append("")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Forward references (Pydantic v2 rebuild)
# ---------------------------------------------------------------------------

ResearchResponse.model_rebuild()
FundamentalData.model_rebuild()


# --- Symbol / name resolution (v0.3.0 Slice A.4) ------------------------------
class SymbolMatch(BaseModel):
    """A candidate security returned by symbol/name lookup."""

    symbol: str
    name: str = ""
    exchange: str = ""  # yfinance exchange code / display
    quote_type: str = ""  # EQUITY / ETF / MUTUALFUND / INDEX / CURRENCY ...
    market: str = ""  # registry market code (US / UK / IN ...)
    market_name: str = ""  # human-readable market
    currency: str = ""  # registry currency for the market
    score: float = 0.0  # relevance score from the search provider


class SubjectResolution(BaseModel):
    """Result of resolving a free-text subject (a ticker or a company name).

    status:
      - "resolved"  -> `resolved` is the single confident match; run research on it.
      - "ambiguous" -> multiple plausible listings in `candidates`; the user picks.
                       Never a silent guess.
      - "not_found" -> nothing usable matched.
    """

    query: str
    status: str
    resolved: SymbolMatch | None = None
    candidates: list[SymbolMatch] = Field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# ETF Metadata (Slice B-B)
# ---------------------------------------------------------------------------


class ETFTopHolding(BaseModel):
    """A single top holding within an ETF."""

    symbol: str = ""
    name: str = ""
    weight: Decimal | None = None  # fraction of fund NAV (0..1)


class ETFMetadata(BaseModel):
    """ETF-specific metadata sourced from the market-data provider.

    Every field degrades to None / empty with an explicit data gap when the
    source does not supply it — the engine and renderer never invent ETF facts.
    """

    ticker: str
    expense_ratio: Decimal | None = None  # fraction, e.g. 0.0009 = 0.09%
    distribution_yield: Decimal | None = None  # fraction, e.g. 0.015 = 1.5%
    aum: Decimal | None = None  # net assets, in profile currency
    tracking_index: str = ""  # underlying index / fund category
    fund_family: str = ""  # issuer / fund family
    top_holdings: list[ETFTopHolding] = Field(default_factory=list)
    sector_weights: dict[str, Decimal] = Field(default_factory=dict)  # sector -> fraction
    data_gaps: list[str] = Field(default_factory=list)
