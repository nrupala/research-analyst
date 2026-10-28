# Copyright (C) 2026 2351485 ALBERTA INC.
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

"""Technical analysis engine — synthesizes raw indicators into actionable signals.

The TechnicalProvider computes raw numbers. This engine interprets them:
  - Multi-timeframe signal aggregation
  - Trend strength scoring
  - Momentum regime classification
  - Volatility context assessment
  - Composite technical score

Design:
  - Input: TechnicalIndicators (from provider)
  - Output: TechnicalAnalysis (scored, interpreted signals)
  - Stateless, deterministic, no external calls
"""
# Module: research_analyst/engines/technical.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..models import Assumption, PriceSeries, TechnicalIndicators

logger = logging.getLogger(__name__)


@dataclass
class TechnicalSignal:
    """Single technical signal with interpretation."""

    indicator: str
    value: str
    signal: str  # "bullish" / "bearish" / "neutral"
    strength: str  # "strong" / "moderate" / "weak"
    description: str


@dataclass
class TechnicalAnalysis:
    """Structured output of technical analysis."""

    ticker: str = ""

    # Composite scores (0-100)
    trend_score: float = 50.0  # 0=strong downtrend, 100=strong uptrend
    momentum_score: float = 50.0  # 0=oversold, 100=overbought
    volatility_score: float = 50.0  # 0=low vol, 100=high vol

    # Overall
    composite_score: float = 50.0  # Weighted blend
    regime: str = ""  # "bullish" / "bearish" / "neutral" / "transitioning"

    # Individual signals
    signals: list[TechnicalSignal] = field(default_factory=list)

    # Price context
    current_price: float | None = None  # None = no price data from the source
    distance_from_52w_high_pct: float = 0.0
    distance_from_52w_low_pct: float = 0.0

    # Key levels
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    support_distance_pct: float | None = None
    resistance_distance_pct: float | None = None

    # Patterns
    patterns: list[str] = field(default_factory=list)

    # Traceability
    assumptions: list[Assumption] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


class TechnicalEngine:
    """Synthesizes technical indicators into scored signals.

    Usage:
        engine = TechnicalEngine()
        analysis = engine.analyze(indicators, price_series)
    """

    # Signal weights for composite score
    _WEIGHTS = {
        "trend": 0.35,
        "momentum": 0.30,
        "volatility": 0.15,
        "volume": 0.20,
    }

    def analyze(
        self,
        indicators: TechnicalIndicators,
        series: PriceSeries,
    ) -> TechnicalAnalysis:
        """Run technical analysis on computed indicators.

        Steps:
          1. Score trend (SMA alignment, ADX, price position)
          2. Score momentum (RSI, MACD, crossovers)
          3. Score volatility (Bollinger, ATR)
          4. Score volume (OBV, volume trend)
          5. Compute composite and classify regime
          6. Identify key levels and patterns
        """
        result = TechnicalAnalysis(
            ticker=indicators.ticker,
            current_price=series.current_price,
            patterns=indicators.patterns_detected,
        )

        if not series.data:
            result.data_gaps.append("No price data available for technical analysis.")
            return result

        # ---- Price context ----
        if series.current_price and series.price_52w_high:
            result.distance_from_52w_high_pct = (
                series.current_price - series.price_52w_high
            ) / series.price_52w_high
        if series.current_price and series.price_52w_low:
            result.distance_from_52w_low_pct = (
                series.current_price - series.price_52w_low
            ) / series.price_52w_low

        # ---- Key levels ----
        if indicators.support_levels:
            result.nearest_support = indicators.support_levels[0]
            if result.nearest_support and series.current_price:
                result.support_distance_pct = (
                    series.current_price - result.nearest_support
                ) / series.current_price
        if indicators.resistance_levels:
            result.nearest_resistance = indicators.resistance_levels[0]
            if result.nearest_resistance and series.current_price:
                result.resistance_distance_pct = (
                    result.nearest_resistance - series.current_price
                ) / series.current_price

        # ---- 1. Trend Score ----
        trend_points = 0.0
        trend_max = 0.0

        # SMA 200 position
        if indicators.price_vs_sma_200:
            trend_max += 30
            trend_points += 30 if indicators.price_vs_sma_200 == "above" else 0

        # SMA 50/200 cross
        if indicators.sma_50_vs_200:
            trend_max += 25
            if indicators.sma_50_vs_200 == "golden_cross":
                trend_points += 25
            elif indicators.sma_50_vs_200 == "death_cross":
                trend_points += 0
            else:
                trend_points += 12.5

        # ADX (trend strength)
        if indicators.adx_14 is not None:
            trend_max += 25
            if indicators.adx_signal == "strong_trend":
                # Strong trend — direction matters
                if indicators.price_vs_sma_200 == "above":
                    trend_points += 25
                else:
                    trend_points += 5
            elif indicators.adx_signal == "weak_trend":
                trend_points += 12.5
            else:
                trend_points += 10

        # 52-week position
        trend_max += 20
        if (
            series.current_price
            and series.price_52w_high
            and series.price_52w_low
            and series.price_52w_high > series.price_52w_low
        ):
            position = (series.current_price - series.price_52w_low) / (
                series.price_52w_high - series.price_52w_low
            )
            trend_points += position * 20

        result.trend_score = (trend_points / trend_max * 100) if trend_max > 0 else 50.0

        # Signal entries for trend
        self._add_signal(
            result,
            "SMA 200",
            indicators.price_vs_sma_200,
            "bullish" if indicators.price_vs_sma_200 == "above" else "bearish",
            "moderate",
            f"Price is {indicators.price_vs_sma_200} the 200-day SMA.",
        )
        self._add_signal(
            result,
            "SMA 50/200 Cross",
            indicators.sma_50_vs_200,
            "bullish"
            if indicators.sma_50_vs_200 == "golden_cross"
            else ("bearish" if indicators.sma_50_vs_200 == "death_cross" else "neutral"),
            "strong" if indicators.sma_50_vs_200 != "neutral" else "weak",
            f"50/200 SMA relationship: {indicators.sma_50_vs_200}.",
        )

        # ---- 2. Momentum Score ----
        mom_points = 0.0
        mom_max = 0.0

        # RSI
        if indicators.rsi_14 is not None:
            mom_max += 35
            # Map RSI to 0-35 score (30=oversold→bullish, 70=overbought→bearish)
            if indicators.rsi_14 < 30:
                mom_points += 30  # Oversold = bullish opportunity
            elif indicators.rsi_14 < 50:
                mom_points += 20
            elif indicators.rsi_14 < 70:
                mom_points += 15
            else:
                mom_points += 5  # Overbought = bearish

            self._add_signal(
                result,
                "RSI (14)",
                f"{indicators.rsi_14:.1f}",
                indicators.rsi_signal or "neutral",
                "strong" if indicators.rsi_14 < 30 or indicators.rsi_14 > 70 else "moderate",
                f"RSI at {indicators.rsi_14:.1f} — {indicators.rsi_signal}.",
            )

        # MACD
        if indicators.macd is not None:
            mom_max += 35
            if indicators.macd_crossover == "bullish":
                mom_points += 35
            elif indicators.macd_crossover == "bearish":
                mom_points += 5
            elif indicators.macd_histogram is not None and indicators.macd_histogram > 0:
                mom_points += 25
            else:
                mom_points += 10

            self._add_signal(
                result,
                "MACD",
                f"{indicators.macd:.4f}",
                indicators.macd_crossover if indicators.macd_crossover != "none" else "neutral",
                "strong" if indicators.macd_crossover != "none" else "moderate",
                f"MACD crossover: {indicators.macd_crossover}.",
            )

        # YTD return momentum
        mom_max += 30
        ytd_return = series.ytd_return if series.ytd_return is not None else 0.0
        if ytd_return > 0.15:
            mom_points += 30
        elif ytd_return > 0:
            mom_points += 20
        elif ytd_return > -0.10:
            mom_points += 10
        else:
            mom_points += 0

        result.momentum_score = (mom_points / mom_max * 100) if mom_max > 0 else 50.0

        # ---- 3. Volatility Score ----
        vol_points = 0.0
        vol_max = 0.0

        # Bollinger position
        if indicators.bollinger_position:
            vol_max += 40
            if indicators.bollinger_position == "above_upper":
                vol_points += 40  # High volatility / extended
            elif indicators.bollinger_position == "below_lower":
                vol_points += 35
            else:
                vol_points += 15

        # ATR as % of price
        if indicators.atr_pct is not None:
            vol_max += 40
            if indicators.atr_pct > 4.0:
                vol_points += 40  # Very high volatility
            elif indicators.atr_pct > 2.0:
                vol_points += 25
            elif indicators.atr_pct > 1.0:
                vol_points += 15
            else:
                vol_points += 5

        # ADX magnitude
        if indicators.adx_14 is not None:
            vol_max += 20
            if indicators.adx_14 > 40:
                vol_points += 20
            elif indicators.adx_14 > 25:
                vol_points += 12
            else:
                vol_points += 5

        result.volatility_score = (vol_points / vol_max * 100) if vol_max > 0 else 50.0

        # ---- 4. Volume context ----
        vol_signal = "neutral"
        if indicators.obv_trend == "accumulation" and indicators.volume_trend == "increasing":
            vol_signal = "bullish"
        elif indicators.obv_trend == "distribution" and indicators.volume_trend == "increasing":
            vol_signal = "bearish"

        self._add_signal(
            result,
            "Volume / OBV",
            indicators.obv_trend,
            vol_signal,
            "moderate",
            f"OBV trend: {indicators.obv_trend}. Volume trend: {indicators.volume_trend}.",
        )

        # ---- 5. Composite Score ----
        volume_score = 50.0
        if vol_signal == "bullish":
            volume_score = 70.0
        elif vol_signal == "bearish":
            volume_score = 30.0

        result.composite_score = (
            self._WEIGHTS["trend"] * result.trend_score
            + self._WEIGHTS["momentum"] * result.momentum_score
            + self._WEIGHTS["volatility"] * (100 - result.volatility_score)  # Lower vol = better
            + self._WEIGHTS["volume"] * volume_score
        )

        # ---- 6. Regime Classification ----
        if result.composite_score >= 65:
            result.regime = "bullish"
        elif result.composite_score >= 45:
            result.regime = "neutral"
        elif result.composite_score >= 30:
            result.regime = "transitioning"
        else:
            result.regime = "bearish"

        # ---- Assumptions ----
        result.assumptions.append(
            Assumption(
                label="Technical Scoring Weights",
                value=f"Trend: {self._WEIGHTS['trend']:.0%}, Momentum: "
                f"{self._WEIGHTS['momentum']:.0%}, "
                f"Volatility: {self._WEIGHTS['volatility']:.0%}, Volume: "
                f"{self._WEIGHTS['volume']:.0%}",
                source="Engine default weights",
            )
        )
        result.assumptions.append(
            Assumption(
                label="Composite Score",
                value=f"{result.composite_score:.1f}/100 ({result.regime})",
                source="Weighted blend of trend, momentum, volatility, volume scores",
            )
        )

        return result

    @staticmethod
    def _add_signal(
        result: TechnicalAnalysis,
        indicator: str,
        value: str,
        signal: str,
        strength: str,
        description: str,
    ) -> None:
        """Add a signal entry if the value is non-empty."""
        if value:
            result.signals.append(
                TechnicalSignal(
                    indicator=indicator,
                    value=value,
                    signal=signal,
                    strength=strength,
                    description=description,
                )
            )
