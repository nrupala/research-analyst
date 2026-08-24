"""Slice A.2 tests: SEC-query gating + reporting-currency metadata (offline, no network)."""
# Module: tests/test_intl_a2.py | Version: 0.3.0 | Slice A.2
from research_analyst.providers import markets as m
from research_analyst.models import ResearchMetadata


def test_should_query_sec_us_only():
    assert m.should_query_sec("AAPL") is True
    assert m.should_query_sec("BRK.B") is True       # US class share, not an exchange suffix
    assert m.should_query_sec("RELIANCE.NS") is False
    assert m.should_query_sec("BP.L") is False
    assert m.should_query_sec("7203.T") is False


def test_metadata_market_currency_defaults():
    md = ResearchMetadata()
    assert md.market == ""
    assert md.reporting_currency == "USD"


def test_metadata_accepts_intl_currency():
    md = ResearchMetadata(market="India (NSE)", reporting_currency="INR")
    assert md.market == "India (NSE)"
    assert md.reporting_currency == "INR"
