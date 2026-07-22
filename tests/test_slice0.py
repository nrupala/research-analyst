"""Slice 0 (data-integrity) regression tests.

Covers the two bugs found in the live AAPL pull:
  - RC2: empty Competitive/Moat step (target had no comparable metrics)
  - Bug 2: macro step "unknown" (FRED never wired) -> FRED client parsing

Offline only: no network. FRED transport is mocked.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from research_analyst.engines.competitor import CompetitorEngine
from research_analyst.models import CompanyProfile, Competitor
from research_analyst.providers.market_data import (
    _fred_observations,
    _sector_peer_candidates,
)

SEC = 'equity'


def _profile():
    return CompanyProfile(
        ticker="AAPL",
        name="Apple Inc.",
        security_type=SEC,
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3_000_000_000_000,
    )


def _peers():
    return [
        Competitor(ticker="MSFT", name="Microsoft", market_cap=2_800_000_000_000,
                   gross_margin=0.69, operating_margin=0.42, roe=0.38,
                   revenue_growth_yoy=0.15, debt_to_equity=0.5, pe_ratio=35.0),
        Competitor(ticker="NVDA", name="NVIDIA", market_cap=2_500_000_000_000,
                   gross_margin=0.73, operating_margin=0.54, roe=0.90,
                   revenue_growth_yoy=1.20, debt_to_equity=0.4, pe_ratio=55.0),
        Competitor(ticker="ORCL", name="Oracle", market_cap=400_000_000_000,
                   gross_margin=0.72, operating_margin=0.30, roe=0.60,
                   revenue_growth_yoy=0.07, debt_to_equity=6.0, pe_ratio=30.0),
        Competitor(ticker="CRM", name="Salesforce", market_cap=270_000_000_000,
                   gross_margin=0.76, operating_margin=0.20, roe=0.10,
                   revenue_growth_yoy=0.11, debt_to_equity=0.2, pe_ratio=45.0),
    ]


def _fundamental():
    return SimpleNamespace(
        gross_margin_latest=0.44,
        operating_margin_latest=0.30,
        net_margin_latest=0.25,
        roe_latest=1.5,
        roic_latest=0.55,
        revenue_growth_yoy=0.08,
        debt_to_equity=1.2,
    )


def test_curated_peer_map_known_sector():
    peers = _sector_peer_candidates("Technology")
    assert len(peers) >= 3
    assert "MSFT" in peers


def test_curated_peer_map_unknown_sector_is_empty():
    assert _sector_peer_candidates("Nonexistent Sector") == []


def test_target_metrics_populated_from_fundamental():
    engine = CompetitorEngine()
    result = engine.analyze(_profile(), _peers(), fundamental=_fundamental())
    assert len(result.rankings) > 0
    metrics = {r.metric for r in result.rankings}
    assert "Gross Margin" in metrics
    assert result.landscape.target.gross_margin == 0.44
    assert result.landscape.target.roic == 0.55


def test_rankings_empty_without_fundamental():
    engine = CompetitorEngine()
    result = engine.analyze(_profile(), _peers())
    ranked = {r.metric for r in result.rankings}
    assert "Gross Margin" not in ranked


def test_no_peers_emits_honest_gap():
    engine = CompetitorEngine()
    result = engine.analyze(_profile(), [], fundamental=_fundamental())
    assert result.rankings == []
    assert any("Competitive analysis unavailable" in g for g in result.data_gaps)


def test_fred_observations_parsing_skips_missing():
    payload = {"observations": [
        {"date": "2026-06-01", "value": "322.0"},
        {"date": "2026-05-01", "value": "."},
        {"date": "2026-04-01", "value": "318.5"},
    ]}
    fake = MagicMock()
    fake.read.return_value = json.dumps(payload).encode()
    cm = MagicMock()
    cm.__enter__.return_value = fake
    cm.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=cm):
        obs = _fred_observations("CPIAUCSL", "x" * 32, "https://api.stlouisfed.org/fred")
    dates = [d for d, _ in obs]
    assert dates == ["2026-06-01", "2026-04-01"]
    assert obs[0][1] == 322.0
