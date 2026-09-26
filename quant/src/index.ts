// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * ra-quant — the Research Analyst analytical engine.
 *
 * Pure functions over multi-year financial statement series. No I/O, no
 * network, no advice: numbers in, numbers out. See README.md for the
 * data contract and sign conventions.
 */

export * from "./types.js";
export * from "./guards.js";
export * from "./trends.js"; // Phase B — multi-year trends, per-share truth serum
export * from "./dupont.js"; // Phase C — DuPont decomposition + ROE attribution
export * from "./forensics.js"; // Phase C — earnings forensics (Sloan, Altman, Beneish)
export * from "./valuation.js"; // Phase D — DCF, reverse DCF, WACC, multiples
export * from "./allocation.js"; // Phase E — capital allocation track record
export * from "./expected.js"; // Phase F — expected value, tornado, margin of safety
export * from "./lenses/index.js"; // mental-model lenses (Graham…Marks)
