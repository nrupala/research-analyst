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

from .enums import (
    AnalysisDomain,
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

    ticker: str = Field(..., min_length=1, max_length=10, description="Equity or ETF ticker symbol")
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
    market: str = ""                 # resolved market name, e.g. "India (NSE)"; "" == US default
    reporting_currency: str = "USD"  # security trading/quote currency (from profile, else registry)


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
    current_price: float = 0.0
    price_52w_high: float = 0.0
    price_52w_low: float = 0.0
    avg_volume_30d: float = 0.0
    avg_volume_90d: float = 0.0
    ytd_return: float = 0.0
    total_return_1y: float = 0.0


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
    sma_50_vs_200: str = ""     # "golden_cross" / "death_cross" / "neutral"

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
    obv_trend: str = ""     # "accumulation" / "distribution" / "neutral"
    adx_14: float | None = None
    adx_signal: str = ""    # "strong_trend" / "weak_trend" / "no_trend"

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
    impact: str       # "Low" / "Medium" / "High" / "Critical"
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
    current_price: float
    scenarios: list[ValuationScenario] = Field(default_factory=list)
    primary_methodology: str = ""  # "DCF" / "Relative" / "Sum-of-Parts" / "Hybrid"
    variant_perception: VariantPerception | None = None

    def ascii_chart(self) -> str:
        """Generate mandatory ASCII scenario summary."""
        lines: list[str] = []
        if not self.scenarios:
            return ""
        max_price = max(
            (s.implied_price_high or 0) for s in self.scenarios
        ) or 1.0
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
    dividend_rate: float | None = None            # forward annual
    trailing_dividend_rate: float | None = None   # trailing 12 months

    # yfinance .info yield fields (raw, un-normalized) — cross-checks only
    info_dividend_yield: float | None = None
    info_payout_ratio: float | None = None
    five_year_avg_yield: float | None = None      # yfinance reports this as a percent
    etf_ttm_yield: float | None = None            # ETF distribution yield (fraction)

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
    current_yield: float | None = None        # forward, fraction
    trailing_yield: float | None = None       # trailing 12m, fraction
    five_year_avg_yield: float | None = None  # fraction
    annual_dividend_rate: float | None = None  # forward $/share
    ex_dividend_date: date | None = None

    # Growth
    dividend_growth_1y: float | None = None
    dividend_growth_3y_cagr: float | None = None
    dividend_growth_5y_cagr: float | None = None

    # Payout / coverage (trailing basis)
    payout_ratio_eps: float | None = None     # dividends paid / net income
    payout_ratio_fcf: float | None = None     # dividends paid / free cash flow
    eps_coverage: float | None = None         # net income / dividends paid
    fcf_coverage: float | None = None         # free cash flow / dividends paid

    # Consistency
    consecutive_increase_years: int = 0
    had_cut: bool = False
    years_since_cut: int | None = None
    paying_years: int = 0

    # Safety
    safety_score: float | None = None         # 0-100
    safety_grade: str = ""                     # Very Safe / Safe / Borderline / At Risk / Unsafe

    # Yield context
    us_10y_yield: float | None = None
    yield_vs_treasury_spread: float | None = None  # current_yield - 10Y
    peer_median_yield: float | None = None
    yield_vs_peers: str = ""                   # "above" / "below" / "in line"
    attractiveness_rating: str = ""            # Attractive / Fairly Valued / Unattractive / Yield-Trap Risk
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

    visual_type: str  # "plotly" / "mermaid" / "ascii" / "table"
    title: str
    content: str  # Code or markup
    ties_to: str = ""  # Which assumption / scenario / risk this supports
    caption: str = ""


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
    disclaimer: str = (
        "**Disclaimer:**\n"
        "This report is for informational and educational purposes only. "
        "It is not financial advice, investment advice, or a recommendation "
        "to buy or sell any security. "
        "All scenario ranges are assumption-driven illustrations, not predictions."
    )

    def to_markdown(self) -> str:
        """Render full report as Markdown."""
        parts: list[str] = [f"# {self.title}\n"]
        parts.append(f"**Ticker:** {self.ticker} | **Report Type:** {self.report_type.value}")
        parts.append(f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}\n")
        parts.append("---\n")

        for section in self.sections:
            parts.append(f"## Step {section.step_number}: {section.title}\n")
            parts.append(section.content)

            for visual in section.visuals:
                parts.append(f"\n### {visual.title}")
                if visual.visual_type == "plotly_json":
                    parts.append('<div class="plotly-chart-data" data-plotly=\'')
                    parts.append(visual.content)
                    parts.append("'></div>")
                elif visual.visual_type == "mermaid":
                    import base64 as _b64
                    _enc = _b64.b64encode(visual.content.encode()).decode()
                    parts.append(f'<div class="mermaid-data" data-mermaid="{_enc}"></div>')
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
            parts.append(f"**Current Price:** ${self.valuation.current_price:.2f}\n")
            parts.append(f"```\n{self.valuation.ascii_chart()}\n```\n")

            if self.valuation.variant_perception:
                vp = self.valuation.variant_perception
                parts.append("### Variant Perception\n")
                parts.append(f"- **Consensus View:** {vp.consensus_view}")
                parts.append(f"- **Variant View:** {vp.variant_view}")
                parts.append(f"- **Why It Matters:** {vp.why_it_matters}")

        parts.append("---\n")
        parts.append(self.disclaimer)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Forward references (Pydantic v2 rebuild)
# ---------------------------------------------------------------------------

ResearchResponse.model_rebuild()
FundamentalData.model_rebuild()
