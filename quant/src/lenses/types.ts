// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * lenses/types.ts — shared types for the mental-model lens library.
 *
 * Each lens module exports `run(s: StatementSeries, ctx?: LensContext):
 * LensResult`: a structured, attributable read of one company's statements
 * through one investor's framework. Lenses never advise; they report
 * signals with the numbers attached.
 */

/** Market assumptions supplied by the caller; every field may be unknown. */
export interface LensContext {
  /** Equity beta vs the market, e.g. 1.2. Null when unknown. */
  beta: number | null;
  /** Risk-free rate as a decimal, e.g. 0.04 for 4%. Null when unknown. */
  riskFreeRate: number | null;
  /** Equity risk premium as a decimal, e.g. 0.05 for 5%. Null when unknown. */
  equityRiskPremium: number | null;
}

/** Directional read of a single signal. */
export type LensRead = "favor" | "caution" | "neutral";

/** One measured fact inside a lens result. */
export interface LensSignal {
  /** Short label, e.g. "Net-net (NCAV)". */
  label: string;
  /** The measured value, human-formatted, e.g. "1.33× (threshold 0.67×)". */
  value: string;
  /** Directional read. */
  read: LensRead;
  /** One line: what the number means and which rule produced the read. */
  note: string;
}

/** Structured output of one lens. */
export interface LensResult {
  /** Machine key, e.g. "graham". */
  lens: string;
  /** Display name, e.g. "Benjamin Graham — Deep Value". */
  name: string;
  /** 1–3 sentence summary; attribution-safe phrasing required. */
  summary: string;
  /** The measured signals. */
  signals: LensSignal[];
  /** Machine-readable raw values behind the signals (decimals, not %). */
  rawValues: Record<string, number | null>;
  /** Names of inputs that were missing and therefore skipped. */
  missing: string[];
}

/** One peer for Magic Formula ranking (see greenblatt.ts). */
export interface PeerDatum {
  id: string;
  roic: number | null;
  earningsYield: number | null;
}
