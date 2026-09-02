"""Competitor analysis engine — auto-discovery, peer comparison, positioning.

Responsibilities:
  - Organize peer data into structured competitive landscape
  - Compute relative positioning on key metrics
  - Identify competitive advantages and disadvantages
  - Generate peer comparison tables (feeds into report visuals)
  - Second-order competitive dynamics assessment

Design:
  - Input: CompanyProfile + list[Competitor] (from MarketDataProvider)
  - Output: CompetitiveAnalysis with rankings, gaps, and positioning
  - All comparisons are mathematical facts, not opinions
  - Competitive advantages/risks are inferred from metric gaps, not narratives
"""
# Module: research_analyst/engines/competitor.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..models import Assumption, CompanyProfile, CompetitiveLandscape, Competitor

if TYPE_CHECKING:
    from .fundamental import FundamentalAnalysis

logger = logging.getLogger(__name__)


@dataclass
class MetricRanking:
    """Single metric ranking within peer group."""

    metric: str
    target_value: float | None
    peer_median: float | None
    peer_mean: float | None
    rank: int | None = None         # 1 = best
    total_peers: int = 0
    percentile: float | None = None  # 0-100, higher = better
    vs_median: str = ""              # "above" / "below" / "at"
    gap_pct: float | None = None     # % difference from median


@dataclass
class CompetitiveAnalysis:
    """Structured competitive analysis output."""

    ticker: str = ""
    sector: str = ""
    industry: str = ""

    # Landscape
    landscape: CompetitiveLandscape | None = None

    # Rankings
    rankings: list[MetricRanking] = field(default_factory=list)

    # Derived insights (facts, not opinions)
    competitive_advantages: list[str] = field(default_factory=list)
    competitive_disadvantages: list[str] = field(default_factory=list)
    positioning_summary: str = ""

    # Second-order dynamics
    market_share_dynamics: str = ""
    competitive_moat_indicators: list[str] = field(default_factory=list)

    # Traceability
    assumptions: list[Assumption] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


class CompetitorEngine:
    """Analyzes competitive positioning from peer data.

    Usage:
        engine = CompetitorEngine()
        analysis = engine.analyze(profile, peers)
    """

    # Metrics where HIGHER is better
    _HIGHER_IS_BETTER = {
        "gross_margin", "operating_margin", "roe", "roic",
        "revenue_growth_yoy", "free_cash_flow_yield",
    }
    # Metrics where LOWER is better
    _LOWER_IS_BETTER = {
        "pe_ratio", "ev_ebitda", "debt_to_equity",
    }

    def analyze(
        self,
        profile: CompanyProfile,
        peers: list[Competitor],
        fundamental: FundamentalAnalysis | None = None,
    ) -> CompetitiveAnalysis:
        """Run competitive analysis.

        Steps:
          1. Build target Competitor from profile
          2. Rank target vs peers on each metric
          3. Identify advantages and disadvantages
          4. Assess moat indicators
          5. Generate positioning summary
        """
        result = CompetitiveAnalysis(
            ticker=profile.ticker,
            sector=profile.sector,
            industry=profile.industry,
        )

        if not peers:
            result.data_gaps.append(
                "Competitive analysis unavailable: no peer set could be resolved "
                f"for sector '{profile.sector or 'unknown'}'. Assumption used: none - "
                "section omitted rather than shown with fabricated peers."
            )
            return result

        # Build target Competitor and populate its own comparable metrics from
        # fundamental analysis (RC2 fix) so rankings and moat actually compute.
        target = self._target_from_profile(profile, peers, fundamental)

        result.landscape = CompetitiveLandscape(
            target=target,
            peers=peers,
            sector=profile.sector,
            industry=profile.industry,
        )

        # Compute rankings for each comparable metric
        all_companies = [target] + peers
        metrics_to_rank = [
            ("gross_margin", "Gross Margin"),
            ("operating_margin", "Operating Margin"),
            ("roe", "Return on Equity"),
            ("roic", "ROIC"),
            ("pe_ratio", "P/E Ratio"),
            ("ev_ebitda", "EV/EBITDA"),
            ("revenue_growth_yoy", "Revenue Growth (YoY)"),
            ("debt_to_equity", "Debt/Equity"),
            ("free_cash_flow_yield", "FCF Yield"),
        ]

        for attr, label in metrics_to_rank:
            ranking = self._rank_metric(target, peers, attr, label)
            if ranking:
                result.rankings.append(ranking)

        # Market cap ranking
        caps = sorted(
            [(c.ticker, float(c.market_cap or 0)) for c in all_companies],
            key=lambda x: x[1],
            reverse=True,
        )
        for rank, (ticker, _) in enumerate(caps, 1):
            if ticker == profile.ticker:
                result.landscape.target_rank_by_market_cap = rank
                break

        # Revenue ranking
        revs = sorted(
            [(c.ticker, float(c.revenue or 0)) for c in all_companies],
            key=lambda x: x[1],
            reverse=True,
        )
        for rank, (ticker, _) in enumerate(revs, 1):
            if ticker == profile.ticker:
                result.landscape.target_rank_by_revenue = rank
                break

        # ---- Identify Advantages / Disadvantages ----
        for r in result.rankings:
            if r.percentile is not None and r.gap_pct is not None:
                if r.metric in ("P/E Ratio", "EV/EBITDA", "Debt/Equity"):
                    # Lower is better — invert interpretation
                    if r.percentile >= 70:
                        result.competitive_advantages.append(
                            f"{r.metric}: {self._fmt(r.target_value)} vs median "
                            f"{self._fmt(r.peer_median)} ({abs(r.gap_pct):.1f}% lower — favorable)."
                        )
                    elif r.percentile <= 30:
                        result.competitive_disadvantages.append(
                            f"{r.metric}: {self._fmt(r.target_value)} vs median "
                            f"{self._fmt(r.peer_median)} ({abs(r.gap_pct):.1f}% higher — unfavorable)."
                        )
                else:
                    # Higher is better
                    if r.percentile >= 70:
                        result.competitive_advantages.append(
                            f"{r.metric}: {self._fmt(r.target_value)} vs median "
                            f"{self._fmt(r.peer_median)} ({abs(r.gap_pct):.1f}% above peers)."
                        )
                    elif r.percentile <= 30:
                        result.competitive_disadvantages.append(
                            f"{r.metric}: {self._fmt(r.target_value)} vs median "
                            f"{self._fmt(r.peer_median)} ({abs(r.gap_pct):.1f}% below peers)."
                        )

        result.landscape.competitive_advantages = result.competitive_advantages
        result.landscape.competitive_risks = result.competitive_disadvantages

        # ---- Moat Indicators ----
        result.competitive_moat_indicators = self._assess_moat(target, peers, result.rankings)

        # ---- Positioning Summary ----
        adv_count = len(result.competitive_advantages)
        disadv_count = len(result.competitive_disadvantages)
        total_ranked = len(result.rankings)

        if adv_count > disadv_count:
            result.positioning_summary = (
                f"{profile.ticker} holds a favorable competitive position: "
                f"{adv_count} advantages vs {disadv_count} disadvantages across "
                f"{total_ranked} metrics ranked against {len(peers)} peers."
            )
        elif disadv_count > adv_count:
            result.positioning_summary = (
                f"{profile.ticker} faces competitive headwinds: "
                f"{disadv_count} disadvantages vs {adv_count} advantages across "
                f"{total_ranked} metrics ranked against {len(peers)} peers."
            )
        else:
            result.positioning_summary = (
                f"{profile.ticker} is positioned in line with peers: "
                f"{adv_count} advantages and {disadv_count} disadvantages across "
                f"{total_ranked} metrics ranked against {len(peers)} peers."
            )

        # Fix D: honest note when the comparison rests on very few metrics.
        if total_ranked and total_ranked < 3:
            result.data_gaps.append(
                f"Competitive ranking is based on only {total_ranked} metric(s); "
                "peer metric coverage was thin. Assumption used: rankings shown are "
                "directional, not comprehensive."
            )

        # ---- Assumptions ----
        result.assumptions.append(Assumption(
            label="Peer Universe",
            value=f"{len(peers)} peers from {profile.sector} sector",
            source="Curated sector peer map (deterministic); metrics enriched via yfinance",
            confidence="Medium",
            note="Peers selected from a curated large-cap sector map; may not capture all direct competitors.",
        ))

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rank_metric(
        self,
        target: Competitor,
        peers: list[Competitor],
        attr: str,
        label: str,
    ) -> MetricRanking | None:
        """Rank target vs peers on a single metric.

        Returns None if target value is missing.
        Uses O(n log n) sort for ranking.
        """
        target_val = getattr(target, attr, None)
        if target_val is None:
            return None

        peer_vals = [
            getattr(p, attr) for p in peers
            if getattr(p, attr, None) is not None
        ]
        if not peer_vals:
            return None

        all_vals = peer_vals + [target_val]
        is_lower_better = attr in self._LOWER_IS_BETTER

        # Sort for ranking
        sorted_vals = sorted(all_vals, reverse=not is_lower_better)
        rank = sorted_vals.index(target_val) + 1

        # Percentile (higher = better)
        if is_lower_better:
            # Lower is better: count how many are worse (higher)
            worse = sum(1 for v in peer_vals if v > target_val)
        else:
            worse = sum(1 for v in peer_vals if v < target_val)
        percentile = (worse / len(peer_vals) * 100) if peer_vals else 50.0

        # Stats
        import numpy as np
        peer_arr = [float(v) for v in peer_vals]
        median = float(np.median(peer_arr))
        mean = float(np.mean(peer_arr))

        gap_pct = ((target_val - median) / abs(median) * 100) if median != 0 else None
        vs_med = "above" if target_val > median else ("below" if target_val < median else "at")

        return MetricRanking(
            metric=label,
            target_value=float(target_val),
            peer_median=median,
            peer_mean=mean,
            rank=rank,
            total_peers=len(all_vals),
            percentile=percentile,
            vs_median=vs_med,
            gap_pct=gap_pct,
        )

    @staticmethod
    def _target_from_profile(
        profile: CompanyProfile,
        peers: list[Competitor],
        fundamental: FundamentalAnalysis | None = None,
    ) -> Competitor:
        """Create a Competitor for the target, populated with its own
        comparable metrics from fundamental analysis.

        Without these metrics the target has no values to rank, so every
        ranking returns None and the Competitive/Moat step renders empty
        (RC2). Populating margins, ROE, ROIC, revenue growth, and D/E here is
        what makes the section compute.
        """
        kwargs: dict = dict(
            ticker=profile.ticker,
            name=profile.name,
            market_cap=profile.market_cap,
        )
        if fundamental is not None:
            kwargs.update(
                gross_margin=fundamental.gross_margin_latest,
                operating_margin=fundamental.operating_margin_latest,
                roe=fundamental.roe_latest,
                roic=fundamental.roic_latest,
                revenue_growth_yoy=fundamental.revenue_growth_yoy,
                debt_to_equity=fundamental.debt_to_equity,
            )
        return Competitor(**kwargs)

    @staticmethod
    def _assess_moat(
        target: Competitor,
        peers: list[Competitor],
        rankings: list[MetricRanking],
    ) -> list[str]:
        """Identify moat indicators from ranking data.

        Moat signals (factual observations, not opinions):
          - Consistently above-median margins (pricing power)
          - High ROIC relative to peers (capital efficiency)
          - Market cap leadership (scale advantage)
          - Low debt relative to peers (financial flexibility)
        """
        moat_signals: list[str] = []

        for r in rankings:
            if r.percentile is None:
                continue
            if r.metric == "Gross Margin" and r.percentile >= 75:
                moat_signals.append(
                    f"Gross margin in top quartile ({r.target_value:.1%}) — "
                    "consistent with pricing power or cost advantage."
                )
            if r.metric == "ROIC" and r.percentile >= 75:
                moat_signals.append(
                    f"ROIC in top quartile ({r.target_value:.1%}) — "
                    "suggests durable competitive advantage in capital deployment."
                )
            if r.metric == "Operating Margin" and r.percentile >= 75:
                moat_signals.append(
                    f"Operating margin in top quartile ({r.target_value:.1%}) — "
                    "indicates operational efficiency or scale benefits."
                )

        # Market cap leadership
        if target.market_cap and peers:
            max_peer_cap = max(float(p.market_cap or 0) for p in peers)
            if float(target.market_cap or 0) > max_peer_cap:
                moat_signals.append("Market cap leadership among peer group — potential scale moat.")

        return moat_signals

    @staticmethod
    def _fmt(val: float | None) -> str:
        """Format a value for display."""
        if val is None:
            return "N/A"
        if abs(val) < 1:
            return f"{val:.1%}"
        return f"{val:.1f}"
