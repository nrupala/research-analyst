"""Unit tests for the international market registry (offline, no network)."""
# Module: tests/test_markets.py | Version: 0.3.0 | Slice A
from research_analyst.providers import markets as m


def test_us_default():
    assert m.resolve("AAPL").code == "US"
    assert m.resolve("AAPL").currency == "USD"
    assert m.is_us("AAPL") is True


def test_class_share_is_us():
    # a dotted US class share must NOT be treated as an exchange suffix
    assert m.suffix_of("BRK.B") == ""
    assert m.resolve("BRK.B").code == "US"
    assert m.is_us("BRK.B") is True


def test_international_suffixes():
    assert m.resolve("RELIANCE.NS").code == "IN"
    assert m.resolve("RELIANCE.NS").currency == "INR"
    assert m.resolve("BP.L").currency == "GBP"
    assert m.resolve("SAP.DE").currency == "EUR"
    assert m.resolve("7203.T").code == "JP"          # numeric root + suffix
    assert m.resolve("BHP.AX").currency == "AUD"
    assert m.resolve("MC.PA").code == "FR"
    assert m.resolve("0700.HK").currency == "HKD"
    assert m.resolve("SHOP.TO").code == "CA"
    assert m.is_us("SHOP.TO") is False


def test_sector_etf_and_disclaimer_key():
    assert m.resolve("BP.L").sector_etf == "EWU"
    assert m.resolve("RELIANCE.NS").disclaimer_key == "IN"


def test_fx_pair():
    assert m.fx_pair("INR") == "INRUSD=X"
    assert m.fx_pair("GBP") == "GBPUSD=X"
    assert m.fx_pair("USD") is None
    assert m.fx_pair("usd") is None
    assert m.fx_pair("eur", base="usd") == "EURUSD=X"


def test_case_insensitive_suffix():
    assert m.resolve("reliance.ns").currency == "INR"
    assert m.suffix_of(" bp.l ") == ".L"


def test_all_markets_dedup():
    codes = [mk.code for mk in m.all_markets()]
    assert len(codes) == len(set(codes))   # deduped by code
    assert "US" in codes and "IN" in codes and "UK" in codes
