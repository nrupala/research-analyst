<!--
Copyright (C) 2026 2351485 ALBERTA INC. — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Slice B - ETF-as-subject report path

## Status
Option A (minimal) shipped this slice. Option B (full ETF metadata) is a
separate follow-up slice.

## Problem
When the report subject is an ETF (security_type == ETF), the equity-oriented
report should surface ETF-relevant context rather than treating it purely as a
stock.

## Option A (this slice) - from fields we already have
- `engines/etf.py::ETFEngine.analyze(profile)` returns a typed dict:
  fund_overview (description), aum (market_cap as an AUM proxy), assumptions,
  and explicit data_gaps for everything deferred.
- `reports/renderer.py::_build_etf_block(ctx)` renders an "ETF Overview" block
  (Strategy + Assets Under Management, currency-aware via money()), gated
  strictly on SecurityType.ETF and wired into comprehensive Step 1.
- Equity path is byte-identical: the block returns empty for non-ETF subjects.

## Deferred to Option B (next slice)
- ETF-metadata model + provider (yfinance) for real expense ratio, distribution
  yield, AUM, tracking index, and top holdings/sectors.
- Thread the engine output through render() (ctx["etf"]) and extend coverage to
  the tactical and comparative report types.

## Tests (tests/test_etf_subject.py)
- ETFEngine: overview + AUM surfaced; data gaps recorded when fields missing.
- Renderer: ETF Overview present for an ETF subject, absent for an equity.
