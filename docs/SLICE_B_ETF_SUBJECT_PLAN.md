# ETF-as-Subject Report Path Plan (Slice B)

## Overview
When the report subject's `SecurityType == ETF`, we will render an ETF-focused block containing:
- Fund overview (description, strategy)
- Expense ratio
- AUM/net assets
- Distribution/yield (current and trailing)
- Tracking index
- Top holdings/sectors (if available in the data model)

Missing fields will be gracefully skipped without breaking the report generation.

## Data Model Review
From `models.py`:
- **CompanyProfile** contains ETF-specific fields:
  - `description` (fund strategy)
  - `currency` (for monetary formatting)
  - `security_type` (identifies as ETF)
- **DividendData** has ETF-specific fields:
  - `is_etf` flag
  - `etf_ttm_yield` (distribution yield)

## Implementation Approach
1. **Engine**: Create `etf.py` mirroring `dividend.py`:
   - Takes ETF-specific data as input
   - Outputs structured ETF analysis (similar to `DividendAnalysis`)
   - Gracefully skips missing fields

2. **Renderer**: Add `_build_etf_block` in `renderer.py`:
   - Gated on `SecurityType.ETF`
   - Mirrors `_build_dividend_block` structure
   - Uses existing `money()` for monetary values

3. **Integration**: Ensure non-ETF subjects produce byte-identical output.

## Available Fields
- **Required**:
  - `description` (fund strategy)
  - `is_etf` flag
  - `etf_ttm_yield`

- **Optional (gracefully skipped if missing)**:
  - Expense ratio
  - AUM/net assets
  - Tracking index
  - Top holdings/sectors

## Testing Strategy
1. Unit tests for `etf.py` engine
2. Integration test proving:
   - ETF subject includes ETF block
   - Non-ETF subject remains unchanged

## Critical Requirement
- When subject is NOT an ETF, output must be byte-identical to current behavior.