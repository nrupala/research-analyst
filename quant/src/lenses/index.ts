// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * lenses/index.ts — the mental-model lens library.
 *
 * Seven lenses, one per investing framework. Each module exports `run(s,
 * ctx?)` (re-exported here under a distinct name) plus its pure building
 * blocks. {@link runAll} runs every lens over the same statements.
 */

import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult } from "./types.js";

export { run as runGraham } from "./graham.js";
export { grahamNumber, marginOfSafety, netCurrentAssetValue } from "./graham.js";

export { run as runGreenblatt, rankPeers } from "./greenblatt.js";
export type { PeerRank } from "./greenblatt.js";

export { run as runLynch, classify, pegRatio } from "./lynch.js";
export type { LynchClassDetail, LynchClassification } from "./lynch.js";

export { run as runDamodaran, costOfEquity, damodaranWacc, impliedGrowth, releveredBeta,
  unleveredBeta } from "./damodaran.js";

export { run as runBuffett, ownerEarnings } from "./buffett.js";

export { run as runDalio, debtCycleGauge, diversificationFactor, riskParityWeights } from "./dalio.js";
export type { DebtCycleGauge } from "./dalio.js";

export { run as runMarks, cycleGauge, secondLevel } from "./marks.js";
export type { MarksContext, SecondLevelOutcome, SecondLevelResult } from "./marks.js";

export type { LensContext, LensRead, LensResult, LensSignal, PeerDatum } from "./types.js";

import { run as runGraham } from "./graham.js";
import { run as runGreenblatt } from "./greenblatt.js";
import { run as runLynch } from "./lynch.js";
import { run as runDamodaran } from "./damodaran.js";
import { run as runBuffett } from "./buffett.js";
import { run as runDalio } from "./dalio.js";
import { run as runMarks } from "./marks.js";

/**
 * Runs all seven mental-model lenses over one statement series.
 * Each lens is independent: a failure (missing data) in one never affects
 * the others. The optional context is shared (Marks reads forensicFlags
 * when the caller passes a MarksContext).
 */
export function runAll(s: StatementSeries, ctx?: LensContext): LensResult[] {
  return [
    runGraham(s, ctx),
    runGreenblatt(s, ctx),
    runLynch(s, ctx),
    runDamodaran(s, ctx),
    runBuffett(s, ctx),
    runDalio(s, ctx),
    runMarks(s, ctx),
  ];
}
