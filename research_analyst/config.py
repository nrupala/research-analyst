"""Configuration management — environment-driven, no hardcoded secrets."""
# Module: research_analyst/config.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SECConfig(BaseSettings):
    """SEC EDGAR API configuration."""

    user_agent: str = Field(
        default="ResearchAnalyst/0.1 (nrupalakolkar@gmail.com)",
        description="SEC requires a descriptive User-Agent with contact info.",
    )
    base_url: str = "https://efts.sec.gov/LATEST"
    full_text_search_url: str = "https://efts.sec.gov/LATEST/search-index"
    company_url: str = "https://data.sec.gov/submissions"
    xbrl_url: str = "https://data.sec.gov/api/xbrl"
    rate_limit_rps: float = 10.0  # SEC allows 10 req/sec
    request_timeout: float = 30.0

    model_config = {"env_prefix": "RA_SEC_"}


class MarketDataConfig(BaseSettings):
    """Market data provider configuration."""

    # yfinance is the primary free provider — no key needed
    yfinance_enabled: bool = True
    # Alpha Vantage as optional backup
    alpha_vantage_key: str = ""
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    # FRED for macro data
    fred_api_key: str = ""
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    # Cache settings
    cache_ttl_seconds: int = 3600  # 1 hour for price data
    cache_dir: Path = _PROJECT_ROOT / ".cache" / "market_data"

    model_config = {"env_prefix": "RA_MARKET_"}


class AnalysisConfig(BaseSettings):
    """Analysis engine defaults — user can override per request."""

    # Monte Carlo
    mc_simulation_paths: int = Field(default=10_000, ge=1_000, le=100_000)
    mc_time_horizon_years: int = Field(default=5, ge=1, le=30)

    # Technical analysis
    sma_windows: list[int] = [20, 50, 200]
    ema_windows: list[int] = [12, 26]
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    atr_period: int = 14
    adx_period: int = 14

    # Valuation defaults
    risk_free_rate: float = 0.043  # 10Y UST as of 2026
    equity_risk_premium: float = 0.055
    default_wacc: float = 0.09
    terminal_growth_rate: float = 0.025

    # Competitor discovery
    max_competitors: int = 8
    min_market_cap_ratio: float = 0.1  # At least 10% of target's market cap

    # Risk scoring
    risk_probability_buckets: list[str] = ["Low (<20%)", "Medium (20-50%)", "High (>50%)"]
    risk_impact_buckets: list[str] = ["Low", "Medium", "High", "Critical"]

    model_config = {"env_prefix": "RA_ANALYSIS_"}

    @field_validator("sma_windows", "ema_windows", mode="before")
    @classmethod
    def _parse_int_list(cls, v: Any) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",")]
        return v


class ServerConfig(BaseSettings):
    """Web server configuration."""

    host: str = "127.0.0.1"
    port: int = 8700
    reload: bool = False
    cors_origins: list[str] = ["http://localhost:8700", "http://127.0.0.1:8700"]
    static_dir: Path = _PROJECT_ROOT / "ui"
    log_level: str = "info"
    # Issue #66: report cache refreshes daily (EOD cadence); entries older
    # than this are regenerated, never silently re-served.
    report_cache_ttl_seconds: int = 86400
    report_cache_max: int = 100

    model_config = {"env_prefix": "RA_SERVER_"}


class BillingConfig(BaseSettings):
    """Paid-feature gating (Phase 8 - simple key issuance, no account system).

    When RA_BILLING_PAID_KEYS is set (comma-separated keys), paid endpoints
    (e.g. source-data download) require a valid X-RA-Key header. When unset,
    the operator has not activated paid gating and the endpoints stay open
    (local/demo use) - activation = setting the env var. No secrets here.
    """

    paid_keys: list[str] = Field(default_factory=list, description="Comma-separated paid API keys.")

    # Key-store file for hashed, revocable API keys (see entitlements.py).
    # Only key hashes are persisted — never raw keys. When set, /api/research/data
    # also accepts KeyStore keys carrying the `source.data` entitlement, and
    # /api/usage serves per-key metering.
    api_keys_file: str = ""

    # White-label branding hooks (evidence is never altered — chrome only).
    white_label_org_name: str = ""
    white_label_prepared_on_url: str = ""
    white_label_footer_note: str = ""
    white_label_show_support_link: bool = True
    white_label_accent_color: str = ""

    model_config = {"env_prefix": "RA_BILLING_"}

    @field_validator("paid_keys", mode="before")
    @classmethod
    def _parse_keys(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v or []


class Settings(BaseSettings):
    """Root settings - aggregates all sub-configs."""

    sec: SECConfig = Field(default_factory=SECConfig)
    market: MarketDataConfig = Field(default_factory=MarketDataConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    billing: BillingConfig = Field(default_factory=BillingConfig)

    # Global
    debug: bool = False
    output_dir: Path = _PROJECT_ROOT / "output"

    model_config = {"env_prefix": "RA_"}

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.market.cache_dir.mkdir(parents=True, exist_ok=True)


# Singleton — import this everywhere
settings = Settings()
