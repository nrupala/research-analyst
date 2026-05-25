"""Technical indicators provider — pure NumPy computation, no external TA libs.

Design principles:
  - All indicators computed from PriceSeries (typed input, typed output)
  - O(n) sliding window algorithms — no naive O(n*k) recomputation
  - EMA uses the standard recursive formula: EMA_t = alpha * price_t + (1 - alpha) * EMA_{t-1}
  - Support/resistance via local extrema detection with configurable lookback
  - Pattern detection is rule-based (double top/bottom, head-and-shoulders heuristics)
  - Every indicator that can be NaN (insufficient data) returns None, never crashes
  - Thread-safe: stateless computation, no mutable class state
"""
# Module: research_analyst/providers/technical.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from datetime import date
from typing import Sequence

import numpy as np

from ..config import settings
from ..models import PriceData, PriceSeries, TechnicalIndicators

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core indicator functions — pure, stateless, O(n)
# ---------------------------------------------------------------------------

def _sma(data: np.ndarray, window: int) -> np.ndarray:
    """Simple Moving Average via cumulative sum — O(n) not O(n*k).

    Returns array of same length as input; first (window-1) values are NaN.
    """
    if len(data) < window:
        return np.full_like(data, np.nan, dtype=np.float64)

    cumsum = np.cumsum(data, dtype=np.float64)
    cumsum[window:] = cumsum[window:] - cumsum[:-window]
    result = np.full_like(data, np.nan, dtype=np.float64)
    result[window - 1:] = cumsum[window - 1:] / window
    return result


def _ema(data: np.ndarray, span: int) -> np.ndarray:
    """Exponential Moving Average — recursive O(n).

    Uses the standard formula:
      alpha = 2 / (span + 1)
      EMA_t = alpha * price_t + (1 - alpha) * EMA_{t-1}
    Initializes with SMA of first `span` values.
    """
    if len(data) < span:
        return np.full_like(data, np.nan, dtype=np.float64)

    alpha = 2.0 / (span + 1)
    result = np.full_like(data, np.nan, dtype=np.float64)

    # Initialize with SMA of first `span` values
    result[span - 1] = np.mean(data[:span])

    # Recursive pass — O(n)
    for i in range(span, len(data)):
        result[i] = alpha * data[i] + (1.0 - alpha) * result[i - 1]

    return result


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index — Wilder's smoothing, O(n).

    RSI = 100 - 100 / (1 + RS)
    RS = avg_gain / avg_loss (Wilder's exponential smoothing)
    """
    if len(closes) < period + 1:
        return np.full_like(closes, np.nan, dtype=np.float64)

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    result = np.full(len(closes), np.nan, dtype=np.float64)

    # First average: simple mean of first `period` values
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - 100.0 / (1.0 + rs)

    # Wilder's smoothing — O(n)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - 100.0 / (1.0 + rs)

    return result


def _macd(
    closes: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD — returns (macd_line, signal_line, histogram).

    MACD = EMA(fast) - EMA(slow)
    Signal = EMA(MACD, signal)
    Histogram = MACD - Signal
    """
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = ema_fast - ema_slow

    # Signal line: EMA of MACD where MACD is valid
    valid_mask = ~np.isnan(macd_line)
    signal_line = np.full_like(macd_line, np.nan)

    if np.sum(valid_mask) >= signal:
        valid_macd = macd_line[valid_mask]
        ema_sig = _ema(valid_macd, signal)
        signal_line[valid_mask] = ema_sig

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger_bands(
    closes: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands — (upper, middle, lower).

    Middle = SMA(period)
    Upper = Middle + std_dev * rolling_std
    Lower = Middle - std_dev * rolling_std

    Rolling std computed via the variance identity: O(n) via cumulative sums.
    """
    middle = _sma(closes, period)

    # Rolling std via cumulative sum of squares — O(n)
    if len(closes) < period:
        nan_arr = np.full_like(closes, np.nan, dtype=np.float64)
        return nan_arr, nan_arr, nan_arr

    cumsum = np.cumsum(closes, dtype=np.float64)
    cumsum_sq = np.cumsum(closes ** 2, dtype=np.float64)

    rolling_var = np.full_like(closes, np.nan, dtype=np.float64)
    rolling_var[period - 1:] = (
        cumsum_sq[period - 1:] - np.concatenate([[0], cumsum_sq[:-period]])
    ) / period - (
        (cumsum[period - 1:] - np.concatenate([[0], cumsum[:-period]])) / period
    ) ** 2

    # Clamp negative variance (floating point artifact)
    rolling_var = np.maximum(rolling_var, 0.0)
    rolling_std = np.sqrt(rolling_var)

    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std

    return upper, middle, lower


def _atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Average True Range — Wilder's smoothing, O(n).

    TR = max(H-L, |H-C_prev|, |L-C_prev|)
    ATR = Wilder's EMA of TR
    """
    if len(closes) < 2:
        return np.full_like(closes, np.nan, dtype=np.float64)

    # True Range
    tr = np.full(len(closes), np.nan, dtype=np.float64)
    tr[0] = highs[0] - lows[0]  # First bar: just H-L

    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    # Wilder's smoothing of TR
    if len(tr) < period + 1:
        return np.full_like(closes, np.nan, dtype=np.float64)

    atr_arr = np.full_like(closes, np.nan, dtype=np.float64)
    atr_arr[period] = np.mean(tr[1: period + 1])  # Skip first NaN-ish

    for i in range(period + 1, len(closes)):
        atr_arr[i] = (atr_arr[i - 1] * (period - 1) + tr[i]) / period

    return atr_arr


def _adx(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Average Directional Index — measures trend strength, O(n).

    ADX = smoothed average of DX
    DX = |+DI - -DI| / (+DI + -DI) * 100
    """
    n = len(closes)
    if n < period * 2:
        return np.full(n, np.nan, dtype=np.float64)

    # Directional movement
    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)

    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0

    atr_vals = _atr(highs, lows, closes, period)

    # Smoothed DM — Wilder's method
    smoothed_plus = np.full(n, np.nan, dtype=np.float64)
    smoothed_minus = np.full(n, np.nan, dtype=np.float64)

    smoothed_plus[period] = np.sum(plus_dm[1:period + 1])
    smoothed_minus[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        smoothed_plus[i] = smoothed_plus[i - 1] - smoothed_plus[i - 1] / period + plus_dm[i]
        smoothed_minus[i] = smoothed_minus[i - 1] - smoothed_minus[i - 1] / period + minus_dm[i]

    # DI+ and DI-
    plus_di = np.full(n, np.nan, dtype=np.float64)
    minus_di = np.full(n, np.nan, dtype=np.float64)

    valid = (~np.isnan(smoothed_plus)) & (~np.isnan(atr_vals)) & (atr_vals > 0)
    plus_di[valid] = (smoothed_plus[valid] / atr_vals[valid]) * 100
    minus_di[valid] = (smoothed_minus[valid] / atr_vals[valid]) * 100

    # DX
    dx = np.full(n, np.nan, dtype=np.float64)
    di_sum = plus_di + minus_di
    valid_dx = (~np.isnan(plus_di)) & (~np.isnan(minus_di)) & (di_sum > 0)
    dx[valid_dx] = (np.abs(plus_di[valid_dx] - minus_di[valid_dx]) / di_sum[valid_dx]) * 100

    # ADX = Wilder's smoothing of DX
    adx_arr = np.full(n, np.nan, dtype=np.float64)

    # Find first valid DX stretch of `period` length
    valid_dx_indices = np.where(~np.isnan(dx))[0]
    if len(valid_dx_indices) < period:
        return adx_arr

    start = valid_dx_indices[period - 1]
    adx_arr[start] = np.mean(dx[valid_dx_indices[:period]])

    for i in range(start + 1, n):
        if not np.isnan(dx[i]) and not np.isnan(adx_arr[i - 1]):
            adx_arr[i] = (adx_arr[i - 1] * (period - 1) + dx[i]) / period

    return adx_arr


def _obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """On-Balance Volume — cumulative, O(n)."""
    if len(closes) < 2:
        return np.array([0.0] * len(closes))

    obv = np.zeros(len(closes), dtype=np.float64)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    return obv


def _find_support_resistance(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    lookback: int = 20,
    num_levels: int = 3,
) -> tuple[list[float], list[float]]:
    """Detect support and resistance levels via local extrema.

    Algorithm:
      1. Find local maxima in highs (resistance candidates)
      2. Find local minima in lows (support candidates)
      3. Cluster nearby levels (within 2% of each other)
      4. Rank by touch count (how many times price tested the level)
      5. Return top `num_levels` of each

    Complexity: O(n) for extrema detection + O(k log k) for sorting candidates.
    """
    n = len(closes)
    if n < lookback * 2:
        return [], []

    # Local maxima in highs
    resistance_candidates: list[float] = []
    for i in range(lookback, n - lookback):
        window = highs[i - lookback: i + lookback + 1]
        if highs[i] == np.max(window):
            resistance_candidates.append(float(highs[i]))

    # Local minima in lows
    support_candidates: list[float] = []
    for i in range(lookback, n - lookback):
        window = lows[i - lookback: i + lookback + 1]
        if lows[i] == np.min(window):
            support_candidates.append(float(lows[i]))

    # Cluster nearby levels — greedy, O(k log k)
    def _cluster(levels: list[float], threshold: float = 0.02) -> list[float]:
        if not levels:
            return []
        sorted_levels = sorted(levels)
        clusters: list[list[float]] = [[sorted_levels[0]]]
        for lv in sorted_levels[1:]:
            if abs(lv - clusters[-1][-1]) / clusters[-1][-1] < threshold:
                clusters[-1].append(lv)
            else:
                clusters.append([lv])
        # Return cluster centers, sorted by cluster size (most tested first)
        centers = [(np.mean(c), len(c)) for c in clusters]
        centers.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in centers[:num_levels]]

    support = _cluster(support_candidates)
    resistance = _cluster(resistance_candidates)

    # Filter: support must be below current price, resistance above
    current = float(closes[-1])
    support = [s for s in support if s < current]
    resistance = [r for r in resistance if r > current]

    return support[:num_levels], resistance[:num_levels]


def _detect_patterns(
    closes: np.ndarray, highs: np.ndarray, lows: np.ndarray
) -> list[str]:
    """Detect common chart patterns — heuristic rule-based, O(n).

    Patterns detected:
      - Double Top / Double Bottom
      - Higher Highs + Higher Lows (uptrend)
      - Lower Highs + Lower Lows (downtrend)
      - Consolidation (narrowing range)
    """
    patterns: list[str] = []
    n = len(closes)

    if n < 60:
        return patterns

    # Last 60 bars for pattern analysis
    recent_highs = highs[-60:]
    recent_lows = lows[-60:]
    recent_closes = closes[-60:]

    # Find local peaks and troughs (5-bar lookback)
    peaks: list[tuple[int, float]] = []
    troughs: list[tuple[int, float]] = []

    for i in range(5, len(recent_highs) - 5):
        if recent_highs[i] == max(recent_highs[i - 5:i + 6]):
            peaks.append((i, float(recent_highs[i])))
        if recent_lows[i] == min(recent_lows[i - 5:i + 6]):
            troughs.append((i, float(recent_lows[i])))

    # Double Top: two peaks within 2% of each other, separated by a trough
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if abs(p1[1] - p2[1]) / p1[1] < 0.02 and p2[0] - p1[0] > 10:
            patterns.append("Double Top (bearish reversal signal)")

    # Double Bottom: two troughs within 2% of each other
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if abs(t1[1] - t2[1]) / t1[1] < 0.02 and t2[0] - t1[0] > 10:
            patterns.append("Double Bottom (bullish reversal signal)")

    # Higher Highs + Higher Lows → Uptrend
    if len(peaks) >= 3 and len(troughs) >= 3:
        hh = all(peaks[i][1] > peaks[i - 1][1] for i in range(-2, 0))
        hl = all(troughs[i][1] > troughs[i - 1][1] for i in range(-2, 0))
        if hh and hl:
            patterns.append("Uptrend (higher highs and higher lows)")

        lh = all(peaks[i][1] < peaks[i - 1][1] for i in range(-2, 0))
        ll = all(troughs[i][1] < troughs[i - 1][1] for i in range(-2, 0))
        if lh and ll:
            patterns.append("Downtrend (lower highs and lower lows)")

    # Consolidation: range narrowing over last 20 bars
    if n >= 20:
        range_first_10 = float(np.max(highs[-20:-10]) - np.min(lows[-20:-10]))
        range_last_10 = float(np.max(highs[-10:]) - np.min(lows[-10:]))
        if range_first_10 > 0 and range_last_10 / range_first_10 < 0.6:
            patterns.append("Consolidation (narrowing range — potential breakout)")

    return patterns


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------

class TechnicalProvider:
    """Computes all technical indicators from PriceSeries.

    Stateless — all configuration comes from settings or method args.
    Thread-safe — no mutable instance state.

    Usage:
        provider = TechnicalProvider()
        indicators = provider.compute(price_series)
    """

    def __init__(self) -> None:
        self._cfg = settings.analysis

    def compute(self, series: PriceSeries) -> TechnicalIndicators:
        """Compute all technical indicators for a PriceSeries.

        Returns a fully populated TechnicalIndicators model.
        Fields that cannot be computed (insufficient data) are left as None.
        Never raises — logs warnings and returns partial results.
        """
        if not series.data:
            logger.warning("Empty PriceSeries for %s — returning blank indicators.", series.ticker)
            return TechnicalIndicators(ticker=series.ticker, as_of_date=date.today())

        # Extract arrays — O(n) single pass
        closes = np.array([p.adj_close for p in series.data], dtype=np.float64)
        highs = np.array([p.high for p in series.data], dtype=np.float64)
        lows = np.array([p.low for p in series.data], dtype=np.float64)
        volumes = np.array([p.volume for p in series.data], dtype=np.float64)
        n = len(closes)
        current = closes[-1]

        # ---- Moving Averages ----
        sma_20 = _sma(closes, 20)
        sma_50 = _sma(closes, 50)
        sma_200 = _sma(closes, 200)
        ema_12 = _ema(closes, 12)
        ema_26 = _ema(closes, 26)

        # ---- Trend signals ----
        price_vs_200 = ""
        if not np.isnan(sma_200[-1]):
            price_vs_200 = "above" if current > sma_200[-1] else "below"

        sma_cross = "neutral"
        if not np.isnan(sma_50[-1]) and not np.isnan(sma_200[-1]):
            if sma_50[-1] > sma_200[-1]:
                sma_cross = "golden_cross"
            elif sma_50[-1] < sma_200[-1]:
                sma_cross = "death_cross"

        # ---- RSI ----
        rsi_arr = _rsi(closes, self._cfg.rsi_period)
        rsi_val = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else None
        rsi_sig = ""
        if rsi_val is not None:
            if rsi_val > 70:
                rsi_sig = "overbought"
            elif rsi_val < 30:
                rsi_sig = "oversold"
            else:
                rsi_sig = "neutral"

        # ---- MACD ----
        macd_line, signal_line, histogram = _macd(
            closes, self._cfg.macd_fast, self._cfg.macd_slow, self._cfg.macd_signal
        )
        macd_val = float(macd_line[-1]) if not np.isnan(macd_line[-1]) else None
        macd_sig_val = float(signal_line[-1]) if not np.isnan(signal_line[-1]) else None
        macd_hist_val = float(histogram[-1]) if not np.isnan(histogram[-1]) else None

        macd_cross = "none"
        if macd_val is not None and macd_sig_val is not None and n >= 2:
            prev_macd = float(macd_line[-2]) if not np.isnan(macd_line[-2]) else None
            prev_sig = float(signal_line[-2]) if not np.isnan(signal_line[-2]) else None
            if prev_macd is not None and prev_sig is not None:
                if prev_macd <= prev_sig and macd_val > macd_sig_val:
                    macd_cross = "bullish"
                elif prev_macd >= prev_sig and macd_val < macd_sig_val:
                    macd_cross = "bearish"

        # ---- Bollinger Bands ----
        bb_upper, bb_middle, bb_lower = _bollinger_bands(
            closes, self._cfg.bollinger_period, self._cfg.bollinger_std
        )
        bb_up = float(bb_upper[-1]) if not np.isnan(bb_upper[-1]) else None
        bb_mid = float(bb_middle[-1]) if not np.isnan(bb_middle[-1]) else None
        bb_low = float(bb_lower[-1]) if not np.isnan(bb_lower[-1]) else None

        bb_pos = ""
        if bb_up is not None and bb_low is not None:
            if current > bb_up:
                bb_pos = "above_upper"
            elif current < bb_low:
                bb_pos = "below_lower"
            else:
                bb_pos = "within"

        # ---- ATR ----
        atr_arr = _atr(highs, lows, closes, self._cfg.atr_period)
        atr_val = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else None
        atr_pct = (atr_val / current * 100) if atr_val and current else None

        # ---- ADX ----
        adx_arr = _adx(highs, lows, closes, self._cfg.adx_period)
        adx_val = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else None
        adx_sig = ""
        if adx_val is not None:
            if adx_val > 25:
                adx_sig = "strong_trend"
            elif adx_val > 15:
                adx_sig = "weak_trend"
            else:
                adx_sig = "no_trend"

        # ---- Volume ----
        vol_trend = "stable"
        if n >= 30:
            avg_recent = np.mean(volumes[-10:])
            avg_prior = np.mean(volumes[-30:-10])
            if avg_prior > 0:
                ratio = avg_recent / avg_prior
                if ratio > 1.2:
                    vol_trend = "increasing"
                elif ratio < 0.8:
                    vol_trend = "decreasing"

        # ---- OBV ----
        obv = _obv(closes, volumes)
        obv_trend = "neutral"
        if n >= 20:
            obv_sma = _sma(obv, 20)
            if not np.isnan(obv_sma[-1]):
                if obv[-1] > obv_sma[-1]:
                    obv_trend = "accumulation"
                else:
                    obv_trend = "distribution"

        # ---- Support / Resistance ----
        support, resistance = _find_support_resistance(highs, lows, closes)

        # ---- Patterns ----
        patterns = _detect_patterns(closes, highs, lows)

        return TechnicalIndicators(
            ticker=series.ticker,
            as_of_date=series.period_end,
            sma_20=float(sma_20[-1]) if not np.isnan(sma_20[-1]) else None,
            sma_50=float(sma_50[-1]) if not np.isnan(sma_50[-1]) else None,
            sma_200=float(sma_200[-1]) if not np.isnan(sma_200[-1]) else None,
            ema_12=float(ema_12[-1]) if not np.isnan(ema_12[-1]) else None,
            ema_26=float(ema_26[-1]) if not np.isnan(ema_26[-1]) else None,
            price_vs_sma_200=price_vs_200,
            sma_50_vs_200=sma_cross,
            rsi_14=rsi_val,
            rsi_signal=rsi_sig,
            macd=macd_val,
            macd_signal=macd_sig_val,
            macd_histogram=macd_hist_val,
            macd_crossover=macd_cross,
            bollinger_upper=bb_up,
            bollinger_middle=bb_mid,
            bollinger_lower=bb_low,
            bollinger_position=bb_pos,
            atr_14=atr_val,
            atr_pct=atr_pct,
            volume_trend=vol_trend,
            obv_trend=obv_trend,
            adx_14=adx_val,
            adx_signal=adx_sig,
            support_levels=support,
            resistance_levels=resistance,
            patterns_detected=patterns,
        )
