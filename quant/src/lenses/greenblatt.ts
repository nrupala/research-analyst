// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * greenblatt.ts — Joel Greenblatt Magic Formula lens (The Little Book That
 * Beats the Market).
 *
 * The Magic Formula ranks companies by the SUM of two ranks: return on
 * capital (quality) and earnings yield (value). This module implements the
 * actual two-factor ranking in {@link rankPeers} and scores a single
 * security on both factors in {@link run}.
 */

import { div, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult, PeerDatum } from "./types.js";
import { fmtPct } from "./util.js";

/**
 * Return on capital (Greenblatt's definition): ebit / investedCapital,
 * where investedCapital = totalEquity + totalDebt − cash (net working
 * capital + net fixed assets proxy). Null when any input is missing or
 * invested capital is 0.
 */
export function greenblattRoic(
  ebit: number | null,
  totalEquity: number | null,
  totalDebt: number | null,
  cash: number | null,
): number | null {
  if (ebit === null || totalEquity === null || totalDebt === null || cash === null) return null;
  const ic = totalEquity + totalDebt - cash;
  if (ic === 0) return null;
  return ebit / ic;
}

/**
 * Earnings yield: ebit / enterpriseValue, with
 * enterpriseValue = price × sharesOutstanding + totalDebt − cash.
 * The "value" half of the Magic Formula. Null when inputs are missing or
 * EV is 0.
 */
export function earningsYield(
  ebit: number | null,
  price: number | null,
  shares: number | null,
  totalDebt: number | null,
  cash: number | null,
): number | null {
  if (ebit === null || price === null || shares === null || totalDebt === null || cash === null) {
    return null;
  }
  const ev = price * shares + totalDebt - cash;
  if (ev === 0) return null;
  return ebit / ev;
}

/** One row of Magic Formula peer ranking output. */
export interface PeerRank {
  id: string;
  /** 1 = best return on capital. Competition ranking (1 + # strictly better); nulls rank last. */
  roicRank: number;
  /** 1 = best earnings yield. Same ranking rule. */
  eyRank: number;
  /** roicRank + eyRank — the Magic Formula composite (lower is better). */
  composite: number;
  /** Final position after sorting by composite ascending (1 = best). */
  order: number;
}

/**
 * The actual Magic Formula ranking (Greenblatt, The Little Book That Beats
 * the Market): rank every peer by return on capital (descending) and by
 * earnings yield (descending), sum the two ranks, and sort by the composite
 * ascending.
 *
 * Ranking rule: competition ranking — rank = 1 + (number of peers strictly
 * better). Ties share a rank; a null factor is treated as worse than every
 * non-null value. Final ties on the composite are broken by id for
 * determinism. Returns one row per peer in final order.
 */
export function rankPeers(peers: PeerDatum[]): PeerRank[] {
  const rankBy = (pick: (p: PeerDatum) => number | null): Map<string, number> => {
    const m = new Map<string, number>();
    for (const p of peers) {
      const v = pick(p);
      let rank = 1;
      for (const q of peers) {
        if (q.id === p.id) continue;
        const w = pick(q);
        // q is strictly better: descending rank, null is worst of all
        if (w !== null && (v === null || w > v)) rank++;
      }
      m.set(p.id, rank);
    }
    return m;
  };

  const roicRank = rankBy((p) => p.roic);
  const eyRank = rankBy((p) => p.earningsYield);

  const rows: PeerRank[] = peers.map((p) => {
    const rr = roicRank.get(p.id) ?? peers.length;
    const er = eyRank.get(p.id) ?? peers.length;
    return { id: p.id, roicRank: rr, eyRank: er, composite: rr + er, order: 0 };
  });
  rows.sort((a, b) => a.composite - b.composite || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  rows.forEach((r, i) => {
    r.order = i + 1;
  });
  return rows;
}

/**
 * Scores one security on the two Magic Formula factors.
 *
 * Quality (return on capital): favor ≥ 20%, caution ≤ 5%, else neutral.
 * Value (earnings yield): favor ≥ 8%, caution ≤ 3%, else neutral.
 * Composite: favor when both favor, caution when either is caution,
 * otherwise neutral. Thresholds are documented heuristics, not Greenblatt's
 * (the formula itself is purely ordinal — it ranks, it does not threshold).
 *
 * Originator: Joel Greenblatt, The Little Book That Beats the Market (2005).
 * Phrasing: "based on principles popularized by Joel Greenblatt
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, _ctx?: LensContext): LensResult {
  const missing: string[] = [];
  const need = (name: string, v: number | null): number | null => {
    if (v === null) missing.push(name);
    return v;
  };

  const ebit = need("ebit", lastValue(s.ebit));
  const equity = need("totalEquity", lastValue(s.totalEquity));
  const debt = need("totalDebt", lastValue(s.totalDebt));
  const cash = need("cash", lastValue(s.cash));
  const price = need("price", lastValue(s.price));
  const shares = need("sharesOutstanding", lastValue(s.sharesOutstanding));

  const roic = greenblattRoic(ebit, equity, debt, cash);
  const ey = earningsYield(ebit, price, shares, debt, cash);

  const readOf = (
    v: number | null,
    favorAt: number,
    cautionAt: number,
  ): "favor" | "caution" | "neutral" =>
    v === null ? "neutral" : v >= favorAt ? "favor" : v <= cautionAt ? "caution" : "neutral";

  const qualityRead = readOf(roic, 0.2, 0.05);
  const valueRead = readOf(ey, 0.08, 0.03);
  const compositeRead =
    roic === null || ey === null
      ? "neutral"
      : qualityRead === "favor" && valueRead === "favor"
        ? "favor"
        : qualityRead === "caution" || valueRead === "caution"
          ? "caution"
          : "neutral";

  return {
    lens: "greenblatt",
    name: "Joel Greenblatt — Magic Formula",
    summary:
      "Two-factor screen based on principles popularized by Joel Greenblatt (public-domain methodology, " +
      "The Little Book That Beats the Market): return on capital (quality) and earnings yield (value). " +
      "Use rankPeers() to run the actual ordinal Magic Formula against a peer set.",
    signals: [
      {
        label: "Quality: return on capital",
        value: fmtPct(roic),
        read: qualityRead,
        note: "ebit / (equity + debt − cash). Favor ≥ 20%, caution ≤ 5% (heuristic thresholds).",
      },
      {
        label: "Value: earnings yield",
        value: fmtPct(ey),
        read: valueRead,
        note: "ebit / enterprise value. Favor ≥ 8%, caution ≤ 3% (heuristic thresholds).",
      },
      {
        label: "Magic Formula composite",
        value:
          roic === null || ey === null
            ? "n/a"
            : `quality ${qualityRead} + value ${valueRead}`,
        read: compositeRead,
        note: "Favor when both factors read favor; caution when either reads caution.",
      },
    ],
    rawValues: { roic, earningsYield: ey },
    missing,
  };
}
