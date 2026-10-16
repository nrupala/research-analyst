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

"""Configuration management — environment-driven, no hardcoded secrets."""
# Module: research_analyst/config.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

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
    # Alpha Vantage — price cascade step 2 (free key tier; see
    # providers/alphavantage.py). Empty key = the step is skipped.
    alpha_vantage_key: str = ""
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    # Tiingo — price cascade step 2, first of the key services (free
    # key tier; see providers/tiingo.py). Empty key = step skipped.
    tiingo_api_key: str = ""
    tiingo_base_url: str = "https://api.tiingo.com"
    # FRED for macro data
    fred_api_key: str = ""
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    # First-source providers (source registry step 1, 2026-10-14) — both
    # keyless official APIs: US Treasury Fiscal Data + Bank of Canada Valet.
    treasury_base_url: str = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
    boc_base_url: str = "https://www.bankofcanada.ca/valet"
    # First-source providers (source registry step 2, 2026-10-14) — all
    # keyless official APIs: ECB + Bundesbank (SDMX), Eurostat, Bank of Japan.
    ecb_base_url: str = "https://data-api.ecb.europa.eu/service"
    bundesbank_base_url: str = "https://api.statistiken.bundesbank.de/rest"
    eurostat_base_url: str = "https://ec.europa.eu/eurostat/api/dissemination"
    boj_base_url: str = "https://www.stat-search.boj.or.jp/api/v1"
    # Stooq free EOD prices — owner-designated production price source
    # (2026-10-14), keyless CSV download; see providers/stooq.py.
    stooq_base_url: str = "https://stooq.com"
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
        return cast("list[int]", v)


class ServerConfig(BaseSettings):
    """Web server configuration."""

    host: str = "127.0.0.1"
    port: int = 8700
    reload: bool = False
    # Browser origins allowed by CORS. The production sites are the default;
    # override with RA_SERVER_CORS_ORIGINS (comma-separated). Never "*": the
    # API accepts credential headers (X-RA-Key / Authorization).
    cors_origins: list[str] = [
        "https://ra.aimlds.org",
        "https://ra.devinfo.dev",
        "https://aimlds.org",
        "https://devinfo.dev",
        "http://localhost:8700",
        "http://127.0.0.1:8700",
    ]
    static_dir: Path = _PROJECT_ROOT / "ui"
    log_level: str = "info"
    # Issue #66: report cache refreshes daily (EOD cadence); entries older
    # than this are regenerated, never silently re-served.
    report_cache_ttl_seconds: int = 86400
    report_cache_max: int = 100

    model_config = {"env_prefix": "RA_SERVER_"}

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v or []


class BillingConfig(BaseSettings):
    """Paid-feature gating (Phase 8 - simple key issuance, no account system).

    Two activation scopes, deliberately separate:
    - RA_BILLING_PAID_KEYS (comma-separated legacy keys) arms every gated
      endpoint, including the metered research/resolve/compare/quant APIs.
    - A KeyStore file (RA_BILLING_API_KEYS_FILE) arms only /api/usage
      (per-key metering for the analysis API), so the free public
      surfaces stay open (release-gate finding H2, 2026-10-15).
    When neither is configured, the operator has not activated paid gating
    and the endpoints stay open (local/demo use). No secrets here.
    """

    paid_keys: list[str] = Field(default_factory=list, description="Comma-separated paid API keys.")

    # Key-store file for hashed, revocable API keys (see entitlements.py).
    # Only key hashes are persisted — never raw keys. When set,
    # /api/usage serves per-key metering for issued keys. It does not
    # gate the public research endpoints.
    api_keys_file: str = ""

    # Metering persistence file (Stream B / F1.2): per-key usage counts
    # survive restarts, so monthly allowances and /api/usage stay true.
    # Defaults to a "metering.json" sibling of the key-store file.
    metering_file: str = ""

    # Stripe billing (Stream A). All values come from the environment —
    # never from code. The billing endpoints stay dormant (503) until
    # stripe_secret_key and stripe_webhook_secret are both set. Card
    # data never touches this service: checkout is Stripe-hosted.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_app_pro: str = ""
    stripe_price_app_team: str = ""
    stripe_price_api_pro: str = ""
    stripe_price_api_team: str = ""
    # Where Stripe sends the buyer after checkout; the success URL must
    # carry the {CHECKOUT_SESSION_ID} placeholder for the claim flow.
    stripe_success_url: str = ""
    stripe_cancel_url: str = ""
    # Paid-checkout grants (session -> plan, claimed state) persist next
    # to the key file by default; overridable for tests/ops.
    stripe_grants_file: str = ""

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


class TelemetryConfig(BaseSettings):
    """First-party telemetry (Stream C) — measurement without tracking.

    Server-side, on-box aggregates + a structured request log (see
    telemetry.py for the content rules: route path only, key record id
    only, no IPs, no query strings, nothing shipped anywhere). The
    operator summary endpoint stays dormant (503) until admin_key is
    set. Retention default 90 days is the operator proposal; the
    owner's pick lands here when Stream D settles the privacy text.
    """

    # State directory for requests-*.jsonl + telemetry.json. Defaults
    # to the key-store file's directory (the state dir), like metering.
    directory: str = ""

    # Operator key for GET /api/telemetry/summary (X-RA-Admin-Key).
    admin_key: str = ""

    retention_days: int = 90

    model_config = {"env_prefix": "RA_TELEMETRY_"}


class Settings(BaseSettings):
    """Root settings - aggregates all sub-configs."""

    sec: SECConfig = Field(default_factory=SECConfig)
    market: MarketDataConfig = Field(default_factory=MarketDataConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    billing: BillingConfig = Field(default_factory=BillingConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

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
