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
// Modules land here as they ship:
// export * from "./trends.js";    // Phase B
// export * from "./dupont.js";    // Phase C
// export * from "./forensics.js"; // Phase C
// export * from "./valuation.js"; // Phase D
// export * from "./allocation.js"; // Phase E
// export * from "./expected.js";   // Phase F
